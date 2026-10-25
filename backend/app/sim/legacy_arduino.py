"""Clock-injected executable specification of the UNO state machine."""

import time
from collections import deque
from app.config import Config


class SimulatedArduino:
    def __init__(self, config: Config | None = None, clock=time.monotonic):
        self.c = config or Config()
        self.clock = clock
        self.events = deque([{"t": "BOOT", "fw": "1.0"}])
        self.uid: str | None = None
        self.pending: tuple | None = None
        self.seq = 0
        self.failures = 0
        self.first_fail: float | None = None
        self.alarm_until = 0.0
        self.last_hb = self.clock()
        self.last_emit = self.clock()
        self.last_scan: dict[str, float] = {}
        self.red_until = 0.0
        self.test_until = 0.0
        self.test_what = ""

    @property
    def pcok(self) -> bool:
        return self.clock() - self.last_hb < self.c.pc_lost_s

    @property
    def alarm(self) -> bool:
        return self.alarm_until > self.clock()

    def emit(self, t: str, **kw) -> None:
        self.events.append({"t": t, **kw})

    def scan(self, uid: str) -> None:
        now = self.clock()
        if self.pending or now - self.last_scan.get(uid, -100) < 1.5:
            return
        self.last_scan[uid] = now
        self.seq = (self.seq + 1) % 65536
        self.pending = (self.seq, uid, now)
        self.emit("SCAN", uid=uid, seq=self.seq)

    def fail(self, uid: str, why: str) -> None:
        now = self.clock()
        if self.first_fail is None or now - self.first_fail >= self.c.fail_window_s:
            self.first_fail, self.failures = now, 0
        self.failures += 1
        self.red_until = now + 2
        self.emit("FAIL", uid=uid, n=self.failures, why=why)
        if self.failures >= self.c.fail_limit:
            self.start_alarm("GATE_3_FAIL")
            self.failures, self.first_fail = 0, None

    def start_alarm(self, why: str) -> None:
        self.alarm_until = self.clock() + self.c.alarm_s
        self.emit("ALARM", why=why)

    def receive(self, m: dict) -> None:
        t = m["t"]
        if t == "HB":
            self.last_hb = self.clock()
        elif (
            t == "AUTH"
            and self.pending
            and m["seq"] == self.pending[0]
            and self.pcok
            and (self.clock() - self.pending[2]) * 1000 < self.c.auth_timeout_ms
        ):
            _, uid, _ = self.pending
            self.pending = None
            if m["ok"]:
                self.failures, self.first_fail = 0, None
                if self.uid and self.uid != uid:
                    self.emit("BUSY", uid=uid)
                elif self.uid:
                    self.uid = None
                    self.emit("SESSION", state="OUT", uid=uid)
                else:
                    self.uid = uid
                    self.emit("SESSION", state="IN", uid=uid)
            else:
                self.fail(uid, "DENY")
        elif t == "REMOVAL" and not self.uid:
            self.start_alarm("SHELF_BREACH")
        elif t == "ALARM" and m.get("on") == 1:
            self.start_alarm("PC_CMD")
        elif t == "ACK":
            self.alarm_until = 0
            self.emit("ALARM_OFF", by="ACK")
        elif t == "SYNC":
            self.uid = m.get("uid") if m["state"] == "IN" else None
        elif t == "CFG":
            for key, field in [
                ("fail_limit", "fail_limit"),
                ("window_s", "fail_window_s"),
                ("alarm_s", "alarm_s"),
            ]:
                if key in m:
                    setattr(
                        self.c,
                        field,
                        max(1, min(int(m[key]), 3600 if key != "fail_limit" else 20)),
                    )
        elif t == "TEST":
            self.test_what, self.test_until = m.get("what", ""), self.clock() + 1

    def tick(self) -> None:
        now = self.clock()
        if self.pending and (now - self.pending[2]) * 1000 >= self.c.auth_timeout_ms:
            _, uid, _ = self.pending
            self.pending = None
            self.fail(uid, "TIMEOUT")
        if (
            self.first_fail is not None
            and now - self.first_fail >= self.c.fail_window_s
        ):
            self.failures, self.first_fail = 0, None
        if self.alarm_until and now >= self.alarm_until:
            self.alarm_until = 0
            self.emit("ALARM_OFF", by="TIMEOUT")
        if now - self.last_emit >= self.c.heartbeat_s:
            self.last_emit = now
            self.emit(
                "HB",
                up=int(now * 1000),
                s="IN" if self.uid else "OUT",
                pcok=int(self.pcok),
            )

    def drain(self) -> list[dict]:
        out = list(self.events)
        self.events.clear()
        return out
