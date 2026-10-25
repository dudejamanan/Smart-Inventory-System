import pytest
from app.sim.arduino import SimulatedArduino
from app.services.protocol import encode, parse, fnv1a, crc16


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


def test_result_codes_and_no_local_toggle():
    c = Clock()
    b = SimulatedArduino(clock=c)
    for r, n in [("IN", 1), ("IN", 2), ("ISS", 2), ("RET", 2), ("OUT", 1)]:
        c.advance(1.6)
        b.receive({"t": "HB", "n": b.n})
        b.scan("A1B2C3D4")
        b.receive({"t": "AUTH", "seq": b.seq, "r": r, "n": n})
        assert b.n == n and b.drain()[-1]["r"] == r
    assert b.n == 1
    b.scan("11223344", rd=0)
    b.receive({"t": "AUTH", "seq": b.seq, "r": "PRM", "n": 1})
    assert b.failures == 0 and b.outputs()["red"]


def test_deadman_pc_silent_and_buttons():
    c = Clock()
    b = SimulatedArduino(clock=c)
    b.receive({"t": "PW", "on": 1, "s": 10})
    c.advance(7)
    b.tick()
    assert not b.pcok and not b.alarm
    b.receive({"t": "PW", "on": 1, "s": 30})
    c.advance(3.1)
    b.tick()
    assert b.alarm and b.alarm_reason == "DEADMAN"
    b.button(True)
    c.advance(0.031)
    b.tick()
    c.advance(0.1)
    b.button(False)
    c.advance(0.031)
    b.tick()
    assert b.alarm and not b.outputs()["buzzer"]
    b.button(True)
    c.advance(0.031)
    b.tick()
    c.advance(1.6)
    b.button(False)
    c.advance(0.031)
    b.tick()
    assert not b.alarm and any(e.get("by") == "BTN" for e in b.drain())
    b.receive({"t": "PW", "on": 1, "s": 1})
    b.receive({"t": "PW", "on": 0})
    c.advance(2)
    b.tick()
    assert not b.alarm


def test_failure_codes_patterns_and_reader_debounce():
    c = Clock()
    b = SimulatedArduino(clock=c, readers=2)
    for r in ["DEN", "PRM", "NSS", "DEN"]:
        c.advance(1.6)
        b.receive({"t": "HB", "n": 0})
        b.scan("DEADBEEF", rd=1)
        b.receive({"t": "AUTH", "seq": b.seq, "r": r, "n": 0})
    assert b.alarm and b.failures == 0
    b.receive({"t": "ACK"})
    b.receive({"t": "ALARM", "on": 1, "why": "SHELF_BREACH"})
    c.advance(0.5)
    assert b.outputs()["buzzer"]
    c.advance(0.15)
    assert not b.outputs()["buzzer"]
    b.receive({"t": "ACK"})
    c.advance(31)
    b.tick()
    assert not b.alarm
    b.receive({"t": "HB", "n": 0})
    b.scan("A1B2C3D4", 0)
    seq = b.seq
    b.receive({"t": "AUTH", "seq": seq, "r": "IN", "n": 1})
    b.scan("A1B2C3D4", 0)
    assert b.seq == seq
    b.scan("A1B2C3D4", 1)
    assert b.seq == seq + 1


@pytest.mark.parametrize(
    "message",
    [
        {"t": "AUTH", "seq": 1, "ok": 1},
        {"t": "AUTH", "seq": 1, "r": "BUSY", "n": 1},
        {"t": "SCAN", "uid": "A1B2C3D4", "seq": 1, "rd": 2},
        {"t": "HB", "n": 9},
        {"t": "WL", "op": "ADD", "h": "abcd0001", "lv": 1, "it": 0},
    ],
)
def test_v2_rejects_invalid(message):
    import json

    with pytest.raises(ValueError):
        parse(json.dumps(message).encode())


def test_v2_bounded_telemetry_and_hash_vectors():
    assert crc16(b"123456789") == 0x29B1
    for m in [
        {"t": "BOOT", "fw": "2.0", "rst": "WDT", "rd": 2, "bid": 4294967295},
        {
            "t": "HB",
            "up": 4294967295,
            "n": 8,
            "pcok": 0,
            "ram": 2048,
            "lp": 4294967295,
            "off": 16,
        },
        {
            "t": "OFF",
            "id": 4294967295,
            "bid": 4294967295,
            "h": "FFFFFFFF",
            "e": "ISS",
            "ago": 4294967,
        },
    ]:
        assert len(encode(m).rstrip(b"\n")) <= 96
    assert fnv1a("A1B2C3D4") != fnv1a("11223344")
