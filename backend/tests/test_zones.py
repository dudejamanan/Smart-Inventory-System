from sqlalchemy import select
from fastapi.testclient import TestClient
from app.config import Config
from app.main import create_app
from app.db.models import Incident, ShelfSlot


def test_zone_permissions_warn_only_when_enabled(tmp_path):
    c = Config(data_dir=tmp_path, admin_password="zone-test-password")
    app = create_app(c, simulate=True, start_services=False)
    r = app.state.runtime
    with TestClient(app) as client:
        client.headers["X-Warehouse-Request"] = "1"
        client.post("/api/login", json={"password": c.admin_password})
        zid = client.post("/api/zones", json={"name": "Restricted electronics"}).json()[
            "id"
        ]
        assert client.get("/api/zones").json()[0]["name"] == "Restricted electronics"
        with r.store.session() as s:
            s.get(ShelfSlot, 1).zone_id = zid
        r.engine.handle({"t": "SESSION", "state": "IN", "uid": "A1B2C3D4"})
        r.engine.slot_change(1, "PRESENT", "ABSENT")
        with r.store.session() as s:
            assert not s.scalars(select(Incident)).all()
        client.put("/api/settings", json={"zones_enabled": True})
        r.engine.slot_change(1, "PRESENT", "ABSENT")
        with r.store.session() as s:
            rows = s.scalars(select(Incident)).all()
            assert (
                len(rows) == 1
                and rows[0].kind == "ZONE_PERMISSION"
                and rows[0].severity == "WARNING"
            )
        assert not r.engine.alarm
        assert (
            client.put("/api/personnel/1/zones", json={"zone_ids": [zid]}).status_code
            == 200
        )
        assert client.get("/api/personnel/1/zones").json()["zone_ids"] == [zid]
        r.engine.slot_change(1, "PRESENT", "ABSENT")
        with r.store.session() as s:
            assert len(s.scalars(select(Incident)).all()) == 1
        assert (
            client.put("/api/personnel/1/zones", json={"zone_ids": [999]}).status_code
            == 422
        )
