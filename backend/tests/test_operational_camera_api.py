import time
from fastapi.testclient import TestClient
from app.config import Config
from app.main import create_app
from app.services.frames import SyntheticShelfSource
from app.services.vision import Vision, detect, classify
from app.db.store import Store
from app.services.engine import Engine


def test_learn_rectifies_complete_pose_and_reveal_markers(tmp_path):
    c = Config(data_dir=tmp_path)
    store = Store(c)
    store.seed()
    src = SyntheticShelfSource()
    src.latest = src.grab()
    src.last_at = time.monotonic()
    engine = Engine(store, c, lambda m: None)
    vision = Vision(src, store, c, engine)
    assert vision.learn()["anchors"] == 4
    src.moved = True
    src.latest = src.grab()
    frame = vision.rectify(src.latest)
    assert vision.rectification == "RECTIFIED" and vision.anchor_residual < 0.02
    markers = detect(frame)
    slot = vision.slots[0]
    roi = (slot.roi_x, slot.roi_y, slot.roi_w, slot.roi_h)
    assert classify(frame, roi, 0, markers, None, 12, mode="both") == "PRESENT"
    src.states[0] = "absent"
    src.latest = src.grab()
    frame = vision.rectify(src.latest)
    assert classify(frame, roi, 0, detect(frame), None, 12, mode="both") == "ABSENT"
    src.states[0] = "occluded"
    src.latest = src.grab()
    frame = vision.rectify(src.latest)
    assert classify(frame, roi, 0, detect(frame), None, 12, mode="reveal") == "OCCLUDED"
    # Hiding anchors suspends classification rather than pretending the fit is valid.
    src.latest[:100] = 0
    src.latest[450:] = 0
    vision.rectify(src.latest)
    assert vision.rectification.startswith("MOVED")
    store.engine.dispose()


def test_two_reader_api_registry_csv_and_calibration_pause(tmp_path):
    c = Config(
        data_dir=tmp_path,
        admin_password="operational-test-password",
        twilio_account_sid="",
        twilio_auth_token="",
    )
    app = create_app(c, simulate=True, start_services=False)
    r = app.state.runtime
    r.engine.firmware_compatible = True  # a compatible BOOT normally sets this
    with TestClient(app) as client:
        assert client.get("/api/ledger.csv").status_code == 401
        client.headers["X-Warehouse-Request"] = "1"
        client.post("/api/login", json={"password": c.admin_password})
        assert (
            client.post(
                "/api/personnel", json={"uid": "01020304", "name": "Duplicate item"}
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/api/inventory",
                json={"name": "Duplicate badge", "marker_id": 4, "tag_uid": "A1B2C3D4"},
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/api/personnel",
                json={"uid": "F1F2F3F4", "name": "Bad level", "level": 4},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/inventory",
                json={"name": "Reveal is not an item", "marker_id": 20},
            ).status_code
            == 422
        )
        for seq, uid, rd in [(1, "A1B2C3D4", 0), (2, "01020304", 1)]:
            r.engine.authorize(dict(t="SCAN", seq=seq, uid=uid, rd=rd))
            result = r.engine.pending_results[seq]["r"]
            r.engine.handle(dict(t="FB", seq=seq, r=result, ms=1))
        assert client.get("/api/ledger").json()[0]["kind"] == "ISSUE"
        assert "ISSUE" in client.get("/api/ledger.csv").text
        assert len(client.get("/api/status").json()["sessions"]) == 1
        assert (
            client.post("/api/calibration/pause", json={"paused": True}).status_code
            == 200
        )
        r.engine.slot_change(2, "PRESENT", "ABSENT")
        assert not r.engine.reconcile.pending
        assert (
            client.post("/api/calibration/pause", json={"paused": False}).status_code
            == 200
        )
        r.engine.slot_change(2, "PRESENT", "ABSENT")
        assert (
            client.post("/api/calibration/pause", json={"paused": True}).status_code
            == 409
        )
        assert (
            client.put(
                "/api/settings", json={"removal_policy": "session_lenient"}
            ).status_code
            == 422
        )
        assert client.post("/api/calibration/learn").status_code == 422  # no live frame


def test_old_schema_additive_upgrade_preserves_history(tmp_path):
    import sqlite3

    path = tmp_path / "warehouse.db"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE personnel(id INTEGER PRIMARY KEY,uid VARCHAR(20) UNIQUE NOT NULL,name VARCHAR(120) NOT NULL,active BOOLEAN NOT NULL,created_at FLOAT)"
        )
        db.execute("INSERT INTO personnel VALUES(1,'A1B2C3D4','Existing',1,100)")
    store = Store(Config(data_dir=tmp_path))
    from app.db.models import Personnel

    with store.session() as s:
        p = s.get(Personnel, 1)
        assert p.name == "Existing" and p.level == 1
    store.engine.dispose()
