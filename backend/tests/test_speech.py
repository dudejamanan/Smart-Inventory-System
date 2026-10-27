import threading
from types import SimpleNamespace
import pytest
from app.config import Config
from app.services.speech import SpeechQueue, Announcer


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeEngine:
    def __init__(self):
        self.calls = []
        self.busy = False
        self.finish = False

    def connect(self, *args):
        pass

    def startLoop(self, *args):
        self.calls.append(("loop", threading.get_ident()))

    def endLoop(self):
        pass

    def iterate(self):
        if self.finish:
            self.busy = False

    def getProperty(self, key):
        return [SimpleNamespace(id="test", name="Test voice")]

    def setProperty(self, key, value):
        self.calls.append((key, value))

    def say(self, text):
        self.calls.append(("say", text))
        self.busy = True

    def isBusy(self):
        return self.busy

    def stop(self):
        self.calls.append(("stop",))
        self.busy = False


def setup(*, simulate=False, capacity=16, **settings):
    c = Config(_env_file=None, **settings)
    clock = Clock()
    engine = FakeEngine()
    speech = SpeechQueue(
        c,
        simulate=simulate,
        engine_factory=lambda: engine,
        clock=clock,
        capacity=capacity,
    )
    return speech, engine, clock


@pytest.mark.parametrize("simulate,enabled", [(True, True), (False, False)])
def test_disabled_and_simulation_never_initialise_audio(simulate, enabled):
    speech, engine, _ = setup(simulate=simulate, tts_enabled=enabled)
    assert not speech.say("x", "Access granted.")
    speech._step()
    assert not engine.calls


def test_alarm_preempts_and_discards_old_successes():
    q, e, c = setup()
    q.say("first", "Access granted.")
    q._step()
    q.say("queued", "Item issued.")
    q.say("alarm", "Security alarm.", priority=0, category="alarm", ttl=20)
    q._step()
    assert ("stop",) in e.calls and e.calls[-1] == ("say", "Security alarm.")
    assert q.status()["interrupted"] == 1 and q.status()["queued"] == 0
    assert ("say", "Item issued.") not in e.calls


def test_expiry_capacity_and_dedup_are_clock_driven():
    q, e, c = setup(capacity=2)
    assert q.say("x", "one") and not q.say("x", "duplicate")
    assert q.say("y", "two") and not q.say("z", "queue full")
    c.advance(7)
    q._step()
    assert not e.calls and q.status()["queued"] == 0
    assert q.status()["dropped"] == 3


def test_mute_stops_current_phrase_and_clears_backlog():
    q, e, c = setup()
    q.say("x", "Access granted.")
    q._step()
    q.say("y", "Item issued.")
    q.c.tts_enabled = False
    q.refresh_settings()
    q._step()
    assert ("stop",) in e.calls and not q.status()["speaking"] and not q.pending


def test_voice_rate_volume_change_applied_on_owner():
    q, e, c = setup(tts_rate=190, tts_volume=0.4, tts_voice="Test voice")
    q.say("x", "Test voice.")
    q._step()
    assert (
        ("rate", 190) in e.calls
        and ("volume", 0.4) in e.calls
        and ("voice", "test") in e.calls
    )


@pytest.mark.parametrize(
    "result,phrase",
    [
        ("IN", "Access granted. Welcome."),
        ("OUT", "Checked out. Goodbye."),
        ("ISS", "Permission granted. Item issued."),
        ("RET", "Item returned. Thank you."),
        ("DEN", "Access denied."),
        ("PRM", "Permission denied. Check the reader and your clearance."),
        ("NSS", "Scan your badge before scanning an item."),
    ],
)
def test_confirmed_feedback_phrase_and_duplicate_suppression(result, phrase):
    q, e, c = setup()
    a = Announcer(q)
    a.serial({"t": "FB", "seq": 1, "r": result, "ms": 1})
    a.serial({"t": "FB", "seq": 1, "r": result, "ms": 1})
    assert len(q.pending) == 1 and q.pending[0].text == phrase


def test_enrolment_is_not_permission_denied_and_boot_resets_sequence_cache():
    q, e, c = setup()
    a = Announcer(q)
    a.serial({"t": "SCAN", "seq": 1}, enrolling=True)
    a.serial({"t": "FB", "seq": 1, "r": "PRM"})
    assert q.pending[0].text.startswith("Tag captured.")
    a.serial({"t": "BOOT", "bid": 2})
    a.serial({"t": "FB", "seq": 1, "r": "IN"})
    assert len(q.pending) == 2


def test_alarm_echo_dedup_ack_and_no_false_warning_cleared():
    q, e, c = setup()
    a = Announcer(q)
    a.command({"t": "PW", "on": 1, "s": 10})
    a.command({"t": "ALARM", "on": 1, "why": "SHELF_BREACH"})
    a.serial({"t": "ALARM", "why": "SHELF_BREACH"})
    a.command({"t": "PW", "on": 0})
    assert len(q.pending) == 1 and q.pending[0].category == "alarm"
    a.serial({"t": "ALARM_OFF", "by": "ACK"})
    assert len(q.pending) == 1 and q.pending[0].text == "Alarm acknowledged."


def test_health_and_warning_announcements_do_not_speak_private_payloads():
    q, e, c = setup()
    a = Announcer(q)
    a.event("CAMERA_HEALTH", {"camera": "shelf", "status": "OK"})
    assert not q.pending
    a.event(
        "CAMERA_HEALTH",
        {"camera": "shelf", "status": "OFFLINE", "detail": "private URL"},
    )
    a.event("INCIDENT", {"kind": "OVERDUE", "uid": "private UID"})
    a.event("INCIDENT", {"kind": "OVERDUE", "uid": "private UID"})
    assert len(q.pending) == 2
    assert all("private" not in m.text for m in q.pending)


def test_audio_worker_failure_isolated_and_bounded_shutdown():
    c = Config(_env_file=None)
    failed = threading.Event()

    def factory():
        failed.set()
        raise OSError("No audio device")

    q = SpeechQueue(c, engine_factory=factory)
    q.start()
    q.say("x", "Access granted.")
    assert failed.wait(1)
    q.close()
    assert not q.thread.is_alive()
    assert "unavailable" in q.status()["error"]


def test_engine_created_and_used_on_one_worker_thread():
    c = Config(_env_file=None)
    created = threading.Event()
    thread_ids = []

    class OwnerEngine(FakeEngine):
        def say(self, text):
            thread_ids.append(threading.get_ident())
            created.set()
            super().say(text)

    def factory():
        thread_ids.append(threading.get_ident())
        return OwnerEngine()

    q = SpeechQueue(c, engine_factory=factory)
    q.start()
    q.say("x", "Voice test.")
    assert created.wait(1)
    q.close()
    assert len(set(thread_ids)) == 1 and thread_ids[0] != threading.get_ident()


def test_tts_failure_cannot_delay_or_prevent_controller_dispatch(tmp_path):
    from app.runtime import Runtime

    r = Runtime(Config(_env_file=None, data_dir=tmp_path), simulate=True)
    sent = []
    r.serial.send = sent.append

    def broken(*args, **kwargs):
        assert sent, "Speech was attempted before controller dispatch"
        raise OSError("Audio failed")

    r.speech.say = broken
    try:
        r.on_serial({"t": "BOOT", "fw": "2.2", "rst": "PWR", "rd": 2, "bid": 1})
        r.on_serial({"t": "SCAN", "uid": "A1B2C3D4", "seq": 1, "rd": 0})
        assert sent[-1] == {"t": "AUTH", "seq": 1, "r": "IN", "n": 1}
        r.on_serial({"t": "FB", "seq": 1, "r": "IN", "ms": 1})
        r.send_command({"t": "ALARM", "on": 1, "why": "SHELF_BREACH"})
        assert sent[-1]["t"] == "ALARM"
    finally:
        r.close()


def test_cancel_during_engine_initialisation_never_speaks_stale_alarm():
    c = Config(_env_file=None)
    engine = FakeEngine()

    def factory():
        q.cancel("alarm")
        return engine

    q = SpeechQueue(c, engine_factory=factory)
    q.say("alarm", "Security alarm.", priority=0, category="alarm")
    q._step()
    assert not any(v[0] == "say" for v in engine.calls)


def test_alarm_arriving_during_initialisation_replaces_popped_success():
    c = Config(_env_file=None)
    engine = FakeEngine()

    def factory():
        q.say("alarm", "Security alarm.", priority=0)
        return engine

    q = SpeechQueue(c, engine_factory=factory)
    q.say("success", "Access granted.")
    q._step()
    q._step()
    assert ("say", "Access granted.") not in engine.calls
    assert ("say", "Security alarm.") in engine.calls


def test_reconciliation_warnings_have_voice_prompts():
    q, e, c = setup()
    a = Announcer(q)
    a.event("RECONCILIATION", {"verdict": "RETURN_UNSCANNED"})
    a.event("RECONCILIATION", {"verdict": "RETURN_NOT_OBSERVED"})
    assert [m.text for m in q.pending] == [
        "Item replaced without a return scan.",
        "Return registered. Please place the item back on its shelf.",
    ]


def test_speech_api_controls_require_auth_and_validate_settings(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app

    c = Config(
        _env_file=None,
        data_dir=tmp_path,
        admin_password="speech-test-password",
        tts_in_simulation=True,
    )
    app = create_app(c, simulate=True, start_services=False)
    with TestClient(app) as client:
        client.headers["X-Warehouse-Request"] = "1"
        assert client.post("/api/test/speech").status_code == 401
        client.post("/api/login", json={"password": c.admin_password})
        assert client.put("/api/settings", json={"tts_volume": 2}).status_code == 422
        assert client.put("/api/settings", json={"tts_rate": 10}).status_code == 422
        assert (
            client.put(
                "/api/settings", json={"tts_enabled": False, "tts_volume": 0.5}
            ).status_code
            == 200
        )
        assert not client.get("/api/status").json()["speech"]["enabled"]
        assert client.post("/api/test/speech").status_code == 409
        assert (
            client.put("/api/settings", json={"tts_enabled": True}).status_code == 200
        )
        assert client.post("/api/test/speech").json()["queued"] is True
