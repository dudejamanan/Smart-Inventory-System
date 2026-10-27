from app.sim.arduino import SimulatedArduino
from test_v2_board import Clock


def test_held_tag_does_not_repeat_when_rf_fields_cycle():
    clock = Clock()
    b = SimulatedArduino(clock=clock, readers=2)
    for _ in range(40):
        b.receive({"t": "HB", "n": 0})
        b.poll_card("A1B2C3D4", 0)
        if b.pending:
            b.receive({"t": "AUTH", "seq": b.seq, "r": "PRM", "n": 0})
        clock.advance(0.1)
    assert b.seq == 1
    clock.advance(0.8)
    b.poll_card("A1B2C3D4", 0)
    assert b.seq == 2


def test_presence_is_independent_for_each_reader():
    c = Clock()
    b = SimulatedArduino(clock=c, readers=2)
    for rd in [0, 1]:
        b.poll_card("A1B2C3D4", rd)
        b.receive({"t": "AUTH", "seq": b.seq, "r": "PRM", "n": 0})
    assert b.seq == 2
    c.advance(0.2)
    b.poll_card("A1B2C3D4", 1)
    assert b.seq == 2
