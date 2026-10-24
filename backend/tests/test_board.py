import pytest
from app.sim.arduino import SimulatedArduino
from app.services.protocol import parse, encode


class Clock:
    t = 0.0

    def __call__(self):
        return self.t

    def advance(self, n):
        self.t += n


def board():
    clock = Clock()
    return SimulatedArduino(clock=clock), clock


def auth(b, c, uid="A1B2C3D4", ok=1):
    c.advance(1.6)
    b.receive({"t": "HB"})
    b.scan(uid)
    b.receive({"t": "AUTH", "seq": b.seq, "ok": ok})


def test_protocol():
    assert parse(encode({"t": "SCAN", "uid": "A1B2C3D4", "seq": 12}))["seq"] == 12
    for raw in [
        b"x",
        b"[]",
        b'{"t":"NO"}',
        b"x" * 97,
        b'{"t":"SCAN","uid":"../a","seq":1}',
    ]:
        with pytest.raises(ValueError):
            parse(raw)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"t":[]}',
        b'{"t":{}}',
        b'{"t":"HB","s":[]}',
        b'{"t":"HB","t":"ACK"}',
        b'{"t":"FAIL","uid":12345678,"n":1,"why":"DENY"}',
        b'{"t":"AUTH","seq":1,"ok":true}',
    ],
)
def test_malformed_field_types(raw):
    with pytest.raises(ValueError):
        parse(raw)


def test_session_busy_removal():
    b, c = board()
    auth(b, c)
    assert b.uid == "A1B2C3D4"
    auth(b, c, "11223344")
    assert b.drain()[-1]["t"] == "BUSY"
    b.receive({"t": "REMOVAL", "slot": 1})
    assert not b.alarm
    auth(b, c)
    assert b.uid is None
    b.receive({"t": "REMOVAL", "slot": 1})
    assert b.alarm
    c.advance(31)
    b.tick()
    assert not b.alarm


def test_fail_reset_window_watchdog():
    b, c = board()
    auth(b, c, ok=0)
    auth(b, c, ok=0)
    assert b.failures == 2
    auth(b, c)
    assert b.failures == 0
    auth(b, c, ok=0)
    c.advance(61)
    b.tick()
    assert b.failures == 0
    for _ in range(3):
        auth(b, c, ok=0)
    assert b.alarm
    b.receive({"t": "ACK"})
    assert not b.alarm
    c.advance(7)
    assert not b.pcok
    b.scan("11223344")
    c.advance(1.1)
    b.tick()
    assert b.drain()[-1]["t"] in {"HB", "FAIL"}
    assert b.failures == 1
    b.receive({"t": "HB"})
    assert b.pcok


def test_wrong_sequence_and_debounce():
    b, c = board()
    b.scan("A1B2C3D4")
    b.receive({"t": "AUTH", "seq": 999, "ok": 1})
    assert b.uid is None
    c.advance(1.1)
    b.tick()
    assert b.failures == 1
    b.scan("A1B2C3D4")
    assert b.pending is None
