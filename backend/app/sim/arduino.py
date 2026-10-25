"""v2 executable board specification; all new behavior uses an injected clock."""

import time
from collections import deque
from app.config import Config
from app.services.protocol import fnv1a

# green pulses/on/off, beep pulses/on/off, red duration (milliseconds).
PATTERNS = {
    "IN": (0, 0, 0, 1, 80, 120, 0),
    "OUT": (2, 150, 150, 2, 80, 120, 0),
    "ISS": (3, 70, 70, 1, 80, 120, 0),
    "RET": (2, 250, 250, 1, 80, 120, 0),
    "DEN": (0, 0, 0, 0, 0, 0, 2000),
    "NSS": (0, 0, 0, 0, 0, 0, 2000),
    "PRM": (0, 0, 0, 2, 80, 120, 2000),
}


class SimulatedArduino:
    def __init__(
        self,
        config: Config | None = None,
        clock=time.monotonic,
        *,
        readers=1,
        eeprom=None,
        boot_id=1,
        use_wdt=True,
        btn_ack=True,
    ):
        self.c = config or Config()
        self.clock = clock
        self.readers = readers
        self.boot_at = clock()
        self.boot_id = boot_id
        self.use_wdt = use_wdt
        self.btn_ack = btn_ack
        self.events = deque()
        self.seq = 0
        self.pending = None
        self.n = 0
        self.last_hb = clock()
        self.last_emit = clock()
        self.last_scan = {}
        self.failures = 0
        self.first_fail = None
        self.alarm_until = 0.0
        self.alarm_reason = ""
        self.pw_until = None
        self.feedback = None
        self.feedback_at = clock()
        self.mute_until = 0.0
        self.test_what = ""
        self.test_until = 0.0
        self.reset_cause = "PWR"
        self.button_raw = False
        self.button_stable = False
        self.button_changed = clock()
        self.button_since = clock()
        self.eeprom = eeprom if eeprom is not None else bytearray(b"\xff" * 1024)
        self.offline_sessions = []
        self.offline_recent = None
        self.logs = deque()
        self.next_id = 1
        self.stage = None
        self.stage_expected = 0
        self.replay_at = -100.0
        self.was_online = True
        self.emit("BOOT", fw="2.0", rst=self.reset_cause, rd=readers, bid=boot_id)

    def emit(self, t, **kw):
        self.events.append({"t": t, **kw})

    @property
    def pcok(self):
        return self.clock() - self.last_hb < self.c.pc_lost_s

    @property
    def alarm(self):
        return self.clock() < self.alarm_until

    @property
    def prewarn(self):
        return self.pw_until is not None

    def drain(self):
        out = list(self.events)
        self.events.clear()
        return out

    def start_alarm(self, why):
        self.alarm_reason = why
        self.alarm_at = self.clock()
        self.alarm_until = self.clock() + self.c.alarm_s
        self.pw_until = None
        self.emit("ALARM", why=why)

    def stop_alarm(self, by):
        self.alarm_until = 0.0
        self.emit("ALARM_OFF", by=by)

    def fail(self, uid, why):
        now = self.clock()
        if self.first_fail is None or now - self.first_fail >= self.c.fail_window_s:
            self.failures = 0
            self.first_fail = now
        self.failures += 1
        self.emit("FAIL", uid=uid, n=self.failures, why=why)
        if self.failures >= self.c.fail_limit:
            self.start_alarm("GATE_3_FAIL")
            self.failures = 0
            self.first_fail = None

    def result(self, r, uid, seq, started):
        self.feedback = r
        self.feedback_at = self.clock()
        if r in {"DEN", "NSS"}:
            self.fail(uid, "NSS" if r == "NSS" else "DENY")
        elif r != "PRM":
            self.failures = 0
            self.first_fail = None
        self.emit("FB", seq=seq, r=r, ms=max(0, int((self.clock() - started) * 1000)))

    def scan(self, uid, rd=0):
        if not 0 <= rd < self.readers:
            raise ValueError("Reader unavailable")
        fnv1a(uid)
        now = self.clock()
        if self.pending or now - self.last_scan.get((rd, uid), -100) < 1.5:
            return
        self.last_scan[(rd, uid)] = now
        self.seq = (self.seq + 1) & 65535
        self.emit("SCAN", uid=uid, seq=self.seq, rd=rd)
        if not self.pcok and self.offline_scan(uid, self.seq, now):
            return
        self.pending = (self.seq, uid, now)

    def offline_scan(self, uid, seq, now):
        return False

    def receive(self, m):
        t = m["t"]
        now = self.clock()
        if t == "HB":
            self.last_hb = now
            self.n = m["n"]
        elif t == "SYNC":
            self.n = m["n"]
        elif (
            t == "AUTH"
            and self.pending
            and m["seq"] == self.pending[0]
            and self.pcok
            and (now - self.pending[2]) * 1000 < self.c.auth_timeout_ms
        ):
            seq, uid, started = self.pending
            self.pending = None
            self.n = m["n"]
            self.result(m["r"], uid, seq, started)
        elif t == "PW":
            if m["on"]:
                deadline = now + m["s"]
                self.pw_until = (
                    deadline if self.pw_until is None else min(deadline, self.pw_until)
                )
                self.pw_at = now
                self.emit("PW", st="ON")
            else:
                self.pw_until = None
                self.emit("PW", st="OFF")
        elif t == "ACK":
            self.stop_alarm("ACK")
            self.pw_until = None
        elif t == "ALARM" and m.get("on") == 1:
            self.start_alarm(m["why"])
        elif t == "CFG":
            self.c.fail_limit = m["fail_limit"]
            self.c.fail_window_s = m["window_s"]
            self.c.alarm_s = m["alarm_s"]
        elif t == "TEST":
            self.test_what = m["what"]
            self.test_until = now + 1

    def button(self, pressed):
        if pressed != self.button_raw:
            self.button_raw = pressed
            self.button_changed = self.clock()

    def tick(self):
        now = self.clock()
        if self.button_raw != self.button_stable and now - self.button_changed >= 0.03:
            self.button_stable = self.button_raw
            if self.button_stable:
                self.button_since = now
            else:
                long = now - self.button_since >= 1.5
                self.emit("BTN", k="L" if long else "S")
                if long and self.btn_ack:
                    self.stop_alarm("BTN")
                    self.pw_until = None
                elif not long:
                    self.mute_until = now + 30
        if self.pending and (now - self.pending[2]) * 1000 >= self.c.auth_timeout_ms:
            seq, uid, started = self.pending
            self.pending = None
            self.feedback = "DEN"
            self.feedback_at = now
            self.fail(uid, "TIMEOUT")
            self.emit("FB", seq=seq, r="DEN", ms=int((now - started) * 1000))
        if (
            self.first_fail is not None
            and now - self.first_fail >= self.c.fail_window_s
        ):
            self.failures = 0
            self.first_fail = None
        if self.pw_until is not None and now >= self.pw_until:
            self.pw_until = None
            self.emit("PW", st="ESC")
            self.start_alarm("DEADMAN")
        if self.alarm_until and now >= self.alarm_until:
            self.stop_alarm("TIMEOUT")
        if now - self.last_emit >= self.c.heartbeat_s:
            self.last_emit = now
            self.emit(
                "HB",
                up=int((now - self.boot_at) * 1000) & 0xFFFFFFFF,
                n=self.n,
                pcok=int(self.pcok),
                ram=0,
                lp=0,
                off=len(self.logs),
            )

    def outputs(self):
        now = self.clock()
        green = self.n > 0
        red = False
        sound = False
        if not self.pcok:
            green = int(now / 0.6) % 2 == 0
            red = not green
        if self.feedback:
            g, on, off, b, bon, boff, r = PATTERNS[self.feedback]
            dt = int((now - self.feedback_at) * 1000)
            if g and dt < g * (on + off):
                green = dt % (on + off) < on
            red |= dt < r
            if b:
                sound = dt < b * (bon + boff) and dt % (bon + boff) < bon
        if self.prewarn:
            phase = int((now - self.pw_at) * 1000) % 1000
            red = phase < 500
            sound |= phase < 80
        if now < self.test_until:
            green |= self.test_what == "green"
            red |= self.test_what == "red"
            sound |= self.test_what == "buzzer"
        if self.alarm:
            dt = int((now - self.alarm_at) * 1000)
            red = dt % 200 < 100
            sound = dt % (
                900 if self.alarm_reason in {"SHELF_BREACH", "DEADMAN"} else 400
            ) < (600 if self.alarm_reason in {"SHELF_BREACH", "DEADMAN"} else 200)
        return {"green": green, "red": red, "buzzer": sound and now >= self.mute_until}
