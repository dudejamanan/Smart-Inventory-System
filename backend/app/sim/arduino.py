"""v2 executable board specification; all new behavior uses an injected clock."""

import time
from collections import deque
from app.config import Config
from app.services.protocol import fnv1a, crc16, whitelist_bytes, encode

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
        boot_id=None,
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
        self.pending_reader = 0
        self.n = 0
        self.last_hb = clock()
        self.last_emit = clock()
        self.last_scan = {}
        self.last_seen = {}
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
        valid = []
        for address in [1008, 1016]:
            value = int.from_bytes(self.eeprom[address : address + 4], "little")
            inverse = int.from_bytes(self.eeprom[address + 4 : address + 8], "little")
            if value and value ^ inverse == 0xFFFFFFFF:
                valid.append((value, address))
        old, address = max(valid) if valid else (0, 1008)
        self.boot_id = boot_id if boot_id is not None else ((old + 1) & 0xFFFFFFFF or 1)
        target = 1008 if address == 1016 else 1016
        self.eeprom[target : target + 8] = self.boot_id.to_bytes(4, "little") + (
            self.boot_id ^ 0xFFFFFFFF
        ).to_bytes(4, "little")
        self.whitelist = self.load_whitelist()
        self.offline_sessions = []
        self.offline_recent = None
        self.logs = deque()
        self.next_id = 1
        self.stage = None
        self.stage_expected = 0
        self.replay_at = -100.0
        self.was_online = True
        self.emit("BOOT", fw="2.2", rst=self.reset_cause, rd=readers, bid=self.boot_id)

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
        if self.pending_reader != 0:
            return
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
        if self.pcok and r in {"IN", "OUT"}:
            self.track_badge(fnv1a(uid), r)
        if r in {"DEN", "NSS"}:
            self.fail(uid, "NSS" if r == "NSS" else "DENY")
        elif r != "PRM":
            self.failures = 0
            self.first_fail = None
        self.emit("FB", seq=seq, r=r, ms=max(0, int((self.clock() - started) * 1000)))

    def poll_card(self, uid, rd=0):
        """Continuous RF observation; scan() represents an explicit re-presentation."""
        if not 0 <= rd < self.readers:
            raise ValueError("Reader unavailable")
        if uid is None or self.pending:
            return
        previous = self.last_seen.get(rd)
        self.last_seen[rd] = (uid, self.clock())
        if previous and previous[0] == uid and self.clock() - previous[1] < 0.6:
            return
        self.scan(uid, rd)

    def scan(self, uid, rd=0):
        if not 0 <= rd < self.readers:
            raise ValueError("Reader unavailable")
        fnv1a(uid)
        now = self.clock()
        previous = self.last_scan.get(rd)
        if self.pending or (
            previous and previous[0] == uid and now - previous[1] < 1.5
        ):
            return
        self.last_scan[rd] = (uid, now)
        self.pending_reader = rd
        self.seq = (self.seq + 1) & 65535
        self.emit("SCAN", uid=uid, seq=self.seq, rd=rd)
        if not self.pcok and self.offline_scan(uid, self.seq, now):
            return
        self.pending = (self.seq, uid, now)

    def load_whitelist(self):
        count = self.eeprom[3]
        if self.eeprom[:2] != b"W2" or self.eeprom[2] != 2 or count > 100:
            return []
        raw = bytes(self.eeprom[2 : 4 + count * 5])
        if crc16(raw) != int.from_bytes(
            self.eeprom[4 + count * 5 : 6 + count * 5], "little"
        ):
            return []
        entries = []
        for i in range(count):
            start = 4 + i * 5
            h = int.from_bytes(self.eeprom[start : start + 4], "little")
            flags = self.eeprom[start + 4]
            if flags & 0x7C or flags & 3 == 0 or any(e[0] == h for e in entries):
                return []
            entries.append((h, flags & 3, bool(flags & 0x80)))
        return entries

    def track_badge(self, h, result):
        hashes = [entry[0] for entry in self.offline_sessions]
        if result == "OUT":
            self.offline_sessions = [e for e in self.offline_sessions if e[0] != h]
            if self.offline_recent and self.offline_recent[0] == h:
                self.offline_recent = None
        elif h not in hashes and len(hashes) < 8:
            level = next(
                (lv for value, lv, it in self.whitelist if value == h and not it), 0
            )
            self.offline_sessions.append((h, level))
        if result == "IN":
            self.offline_recent = (h, self.clock())

    def offline_scan(self, uid, seq, now):
        self.stage = None
        self.was_online = False
        self.n = len(self.offline_sessions)
        if len(self.logs) >= 16 or self.next_id > 0xFFFFFFFF:
            self.emit("WLERR", why="FULL")
            self.result("PRM", uid, seq, now)
            return True
        h = fnv1a(uid)
        entry = next((e for e in self.whitelist if e[0] == h), None)
        result = "DEN"
        event = "DEN"
        if self.readers == 2 and (
            (self.pending_reader == 0 and entry and entry[2])
            or (self.pending_reader == 1 and (not entry or not entry[2]))
        ):
            result = "PRM"
        elif entry:
            _, level, item = entry
            if not item:
                if any(e[0] == h for e in self.offline_sessions):
                    result = "OUT"
                elif len(self.offline_sessions) < 8:
                    result = "IN"
                else:
                    result = "PRM"
                if result in {"IN", "OUT"}:
                    self.track_badge(h, result)
                    event = result
            else:
                owner = None
                if self.offline_recent and now - self.offline_recent[1] < 30:
                    owner = next(
                        (
                            e
                            for e in self.offline_sessions
                            if e[0] == self.offline_recent[0]
                        ),
                        None,
                    )
                if owner is None and len(self.offline_sessions) == 1:
                    owner = self.offline_sessions[0]
                result = (
                    "NSS" if owner is None else "PRM" if owner[1] < level else "ISS"
                )
                if result == "ISS":
                    event = "ISS"
        self.n = len(self.offline_sessions)
        self.logs.append({"id": self.next_id, "h": f"{h:08X}", "e": event, "at": now})
        self.next_id += 1
        self.result(result, uid, seq, now)
        return True

    def whitelist_command(self, m):
        op = m["op"]

        def error(why):
            self.emit("WLERR", why=why)

        if op == "CLR":
            if self.logs or self.alarm or self.prewarn or self.pending or not self.pcok:
                error("BUSY")
                return
            self.stage = []
            self.stage_expected = m["n"]
        elif self.stage is None:
            error("STATE")
        elif op == "ADD":
            if len(self.stage) >= self.stage_expected:
                error("COUNT")
                self.stage = None
                return
            h = int(m["h"], 16)
            if any(e[0] == h for e in self.stage):
                error("DUP")
                self.stage = None
                return
            self.stage.append((h, m["lv"], bool(m["it"])))
        elif op == "END":
            entries = self.stage
            self.stage = None
            if self.alarm or self.prewarn or self.pending:
                error("BUSY")
                return
            if len(entries) != m["n"] or m["n"] != self.stage_expected:
                error("COUNT")
                return
            raw = whitelist_bytes(entries)
            if crc16(raw) != m["ck"]:
                error("CRC")
                return
            self.eeprom[0:2] = b"\x00\x00"
            self.eeprom[2 : 2 + len(raw)] = raw
            self.eeprom[2 + len(raw) : 4 + len(raw)] = m["ck"].to_bytes(2, "little")
            self.eeprom[:2] = b"W2"
            self.whitelist = list(entries)
            levels = {h: lv for h, lv, it in entries if not it}
            self.offline_sessions = [
                (h, levels[h]) for h, _ in self.offline_sessions if h in levels
            ]
            if self.offline_recent and self.offline_recent[0] not in levels:
                self.offline_recent = None
            self.emit("WLOK", n=len(entries))

    def receive(self, m):
        try:
            encode(m)
        except ValueError:
            return
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
        elif t == "WL":
            self.whitelist_command(m)
        elif t == "OFFOK" and self.logs and self.logs[0]["id"] == m["id"]:
            self.logs.popleft()
            self.replay_at = -100.0

    def button(self, pressed):
        if pressed != self.button_raw:
            self.button_raw = pressed
            self.button_changed = self.clock()

    def tick(self):
        now = self.clock()
        if not self.pcok:
            self.stage = None
        if self.pcok and self.logs and now - self.replay_at >= 1:
            self.replay_at = now
            event = self.logs[0]
            self.emit(
                "OFF",
                id=event["id"],
                bid=self.boot_id,
                h=event["h"],
                e=event["e"],
                ago=max(0, int(now - event["at"])),
            )
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
