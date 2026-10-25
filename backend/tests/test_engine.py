from app.config import Config
from app.db.store import Store
from app.db.models import FailedScan, Incident, SecurityEvent
from app.services.engine import Engine
from sqlalchemy import select


def test_alarm_path_survives_camera_notifier_and_db_failure(tmp_path):
    store = Store(Config(data_dir=tmp_path))
    store.seed()
    sent = []
    e = Engine(store, Config(), sent.append)

    def broken(*args):
        raise OSError("camera unavailable")

    e.capture = broken
    e.authorize({"t": "SCAN", "seq": 1, "uid": "A1B2C3D4"})
    assert sent[-1] == {"t": "AUTH", "seq": 1, "r": "IN", "n": 1}
    e.authorize({"t": "SCAN", "seq": 2, "uid": "DEADBEEF"})
    assert sent[-1]["r"] == "DEN"
    # Even database failure happens after the removal command is sent.
    e.event = broken
    try:
        e.slot_change(1, "PRESENT", "ABSENT")
    except OSError:
        pass
    assert sent[-1] == {"t": "ALARM", "on": 1, "why": "SHELF_BREACH"}


def test_fail_and_busy_logging(tmp_path):
    store = Store(Config(data_dir=tmp_path))
    store.seed()
    e = Engine(store, Config(), lambda m: None)
    e.handle({"t": "FAIL", "uid": "DEADBEEF", "n": 1, "why": "DENY"})
    e.handle({"t": "SESSION", "uid": "A1B2C3D4", "state": "IN"})
    assert e.current["name"] == "Aarav Shah"
    e.handle({"t": "BUSY", "uid": "11223344"})
    assert e.current["uid"] == "A1B2C3D4"
    e.slot_change(1, "PRESENT", "ABSENT")
    with store.session() as s:
        assert len(s.scalars(select(FailedScan)).all()) == 1
        assert not s.scalars(select(Incident)).all()
        assert s.scalar(
            select(SecurityEvent).where(SecurityEvent.type == "ITEM_REMOVED")
        )
