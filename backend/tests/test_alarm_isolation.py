import threading
from app.config import Config
from app.db.store import Store
from app.services.engine import Engine
from app.services.frames import SyntheticShelfSource, jpeg
from app.services.vision import Vision, crop
from app.db.models import ShelfSlot


def test_auth_and_removal_dispatch_do_not_wait_for_rules_lock(tmp_path):
    store = Store(Config(data_dir=tmp_path))
    store.seed()
    sent = []
    signal = threading.Event()

    def send(m):
        sent.append(m)
        signal.set()

    e = Engine(store, Config(), send)
    with e.lock:
        auth = threading.Thread(
            target=e.authorize, args=({"t": "SCAN", "seq": 1, "uid": "A1B2C3D4"},)
        )
        auth.start()
        assert signal.wait(1), "AUTH blocked on a database/rules lock"
        signal.clear()
        removal = threading.Thread(target=e.slot_change, args=(1, "PRESENT", "ABSENT"))
        removal.start()
        assert signal.wait(1), "REMOVAL blocked on a database/rules lock"
    auth.join(2)
    removal.join(2)
    assert sent[0]["t"] == "AUTH" and sent[1] == {
        "t": "ALARM",
        "on": 1,
        "why": "SHELF_BREACH",
    }
    store.engine.dispose()


def test_loaded_vision_still_sends_removal_with_database_down(tmp_path, monkeypatch):
    c = Config(data_dir=tmp_path)
    store = Store(c)
    store.seed()
    source = SyntheticShelfSource()
    with store.session() as s:
        slot = s.get(ShelfSlot, 1)
        path = tmp_path / "empty.jpg"
        path.write_bytes(jpeg(crop(source.empty(), (0.06, 0.25, 0.26, 0.55))))
        slot.empty_ref_path = str(path)
    sent = []
    e = Engine(store, c, sent.append)
    vision = Vision(source, store, c, e)
    import time

    source.latest = source.grab()
    source.last_at = time.monotonic()
    for _ in range(5):
        vision.process()
    assert vision.states[1] == "PRESENT"

    def failed_db():
        raise OSError("DB unavailable")

    monkeypatch.setattr(store, "session", failed_db)
    source.states[0] = "absent"
    source.latest = source.grab()
    for _ in range(5):
        try:
            vision.process()
        except OSError:
            pass
    assert {"t": "ALARM", "on": 1, "why": "SHELF_BREACH"} in sent
    store.engine.dispose()
