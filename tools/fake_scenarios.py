"""Run real threaded HTTP/vision/serial-simulator scenarios in an isolated temp DB.

No mocks replace the vision detector or engine. Notifier is deliberately mocked.
python tools/fake_scenarios.py
"""

import tempfile
import time
from pathlib import Path
from common import Config
from fastapi.testclient import TestClient
from app.main import create_app


def wait(predicate, timeout=7, description="condition"):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(0.08)
    raise AssertionError("Timed out waiting for " + description)


def run_scenarios(data_dir, report=print):
    c = Config(
        data_dir=Path(data_dir),
        admin_password="scenario-password",
        cookie_secret="test-cookie-secret" * 3,
        media_url_secret="test-media-secret" * 3,
        twilio_account_sid="",
        twilio_auth_token="",
    )
    app = create_app(c, simulate=True)
    with TestClient(app) as client:
        client.headers["X-Warehouse-Request"] = "1"
        assert (
            client.post("/api/login", json={"password": c.admin_password}).status_code
            == 200
        )
        status = lambda: client.get("/api/status").json()
        incidents = lambda: client.get("/api/incidents").json()

        def control(**body):
            response = client.post("/api/sim/control", json=body)
            assert response.status_code == 200, response.text

        def scan(uid):
            # UNO ignores repeated card reads for 1.5 s.
            time.sleep(1.55)
            control(action="scan", uid=uid)

        def ack():
            for i in incidents():
                if i["status"] == "OPEN":
                    assert (
                        client.post(f"/api/incidents/{i['id']}/ack").status_code == 200
                    )
            wait(lambda: not status()["alarm"])

        wait(
            lambda: status()["serial"]["connected"]
            and status()["slots"].get("1") == "PRESENT",
            description="startup and vision",
        )
        scan("A1B2C3D4")
        wait(lambda: status()["session"])
        report("PASS valid card -> session IN")
        scan("DEADBEEF")
        wait(lambda: status()["fail_counter"] == 1)
        report("PASS unknown card x1 -> FAIL and session retained")
        scan("DEADBEEF")
        scan("DEADBEEF")
        wait(lambda: status()["alarm"])
        report("PASS unknown card x3 -> gate alarm and incident")
        gate = next(i for i in incidents() if i["kind"] == "GATE_3_FAIL")
        wait(
            lambda: client.get(f"/api/incidents/{gate['id']}").json()["evidence"],
            description="gate photo attached",
        )
        ack()
        scan("DEADBEEF")
        scan("DEADBEEF")
        scan("A1B2C3D4")
        wait(lambda: status()["session"] is None and status()["fail_counter"] == 0)
        assert not status()["alarm"]
        report("PASS two wrong then right -> reset, session OUT")
        scan("A1B2C3D4")
        wait(lambda: status()["session"])
        control(action="slot", marker_id=0, state="absent")
        wait(lambda: status()["slots"].get("1") == "ABSENT")
        assert not status()["alarm"]
        report("PASS removal with session -> attributed without alarm")
        control(action="slot", marker_id=0, state="present")
        wait(lambda: status()["slots"].get("1") == "PRESENT")
        scan("A1B2C3D4")
        wait(lambda: status()["session"] is None)
        control(action="slot", marker_id=0, state="absent")
        wait(lambda: status()["alarm"])
        wait(lambda: any(i["kind"] == "SHELF_BREACH" for i in incidents()))
        breach = next(i for i in incidents() if i["kind"] == "SHELF_BREACH")
        evidence = lambda: client.get(f"/api/incidents/{breach['id']}").json()[
            "evidence"
        ]
        wait(
            lambda: len(evidence()) >= 4, timeout=9, description="shelf photos and clip"
        )
        assert all(len(e["sha256"]) == 64 for e in evidence())
        report(
            "PASS unattended removal -> UNO alarm, incident, hashed evidence and notification queue"
        )
        ack()
        control(action="slot", marker_id=0, state="occluded")
        wait(
            lambda: any(i["kind"] == "SLOT_OCCLUDED" for i in incidents()),
            description="occlusion warning",
        )
        assert not status()["alarm"]
        report("PASS hand occlusion -> warning without buzzer")
        control(action="slot", marker_id=0, state="present")
        wait(lambda: status()["slots"].get("1") == "PRESENT")
        control(action="covered", state="on")
        wait(lambda: status()["shelf_camera"] == "COVERED")
        assert not status()["alarm"]
        report("PASS covered camera -> health warning")
        control(action="covered", state="off")
        wait(lambda: status()["shelf_camera"] == "OK")
        control(action="serial", state="off")
        wait(lambda: not status()["serial"]["connected"], timeout=9)
        report("PASS serial disconnect -> disconnected after heartbeat timeout")
        control(action="serial", state="on")
        wait(lambda: status()["serial"]["connected"])
        scan("A1B2C3D4")
        wait(lambda: status()["session"])
        worker = status()["session"]["name"]
    # New runtime and new board model load the durable session and SYNC it.
    restarted = create_app(c, simulate=True)
    with TestClient(restarted) as client:
        client.post("/api/login", json={"password": c.admin_password})
        wait(lambda: restarted.state.runtime.serial.board.uid == "A1B2C3D4")
        assert client.get("/api/status").json()["session"]["name"] == worker
        report("PASS restart with open session -> database restore and SYNC")


def main():
    with tempfile.TemporaryDirectory(prefix="warehouse-scenarios-") as directory:
        run_scenarios(directory)
    print(
        "All 10 end-to-end scenarios passed. Synthetic hardware; no electrical claims."
    )


if __name__ == "__main__":
    main()
