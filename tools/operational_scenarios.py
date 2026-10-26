"""Fast real engine/store/UNO simulator integration with injected domain time."""

from pathlib import Path
import common  # noqa: F401
from sqlalchemy import select
from app.config import Config
from app.db.store import Store
from app.db.models import Reconciliation, Incident
from app.services.engine import Engine
from app.services.frames import SyntheticShelfSource
from app.services.vision import Vision
from app.sim.arduino import SimulatedArduino


class Clock:
    def __init__(self):
        self.now = 1000000.0

    def __call__(self):
        return self.now


class Harness:
    def __init__(self, path):
        self.clock = Clock()
        self.config = Config(
            data_dir=Path(path),
            session_ttl_min=1,
            overdue_check_s=1,
            twilio_account_sid="",
            twilio_auth_token="",
            notify_channels="",
        )
        self.store = Store(self.config)
        self.store.seed()
        self.board = SimulatedArduino(self.config, clock=self.clock, readers=2)
        self.sent = []
        self.engine = Engine(self.store, self.config, self.send, self.clock)
        self.photos = []
        self.alerts = []
        self.engine.capture = lambda *args: self.photos.append(args)
        self.engine.evidence = lambda *args: self.photos.append(args)
        self.engine.alert = lambda *args: self.alerts.append(args)
        self.pump()

    def send(self, m):
        self.sent.append(m)
        self.board.receive(m)

    def pump(self):
        for _ in range(1000):
            if not self.board.events:
                break
            m = self.board.events.popleft()
            self.engine.authorize(m)
            self.engine.handle(m)
        else:
            raise AssertionError("Unexpected serial event loop")
        self.engine.drain()

    def tap(self, uid, reader=0):
        self.clock.now += 1.6
        self.board.receive({"t": "HB", "n": len(self.engine.sessions)})
        self.board.scan(uid, reader)
        self.pump()
        return self.board.feedback

    def advance(self, seconds):
        self.clock.now += seconds
        self.engine.safety_tick()
        self.board.tick()
        self.pump()

    def lift(self, slot=1):
        self.engine.slot_change(slot, "PRESENT", "ABSENT")
        self.pump()

    def verdict(self, expected):
        with self.store.session() as s:
            assert expected in [r.verdict for r in s.scalars(select(Reconciliation))]


def run_operational_scenarios(directory, report=print):
    directory = Path(directory)

    def case(name, run):
        h = Harness(
            directory / str(len(list(directory.glob("*"))) if directory.exists() else 0)
        )
        try:
            run(h)
            report("PASS | operational | " + name)
        finally:
            h.store.engine.dispose()

    def entry(h):
        assert h.tap("A1B2C3D4") == "IN"

    def unknown(h):
        assert h.tap("DEADBEEF") == "DEN"
        assert not h.board.alarm and not h.photos

    def three(h):
        for _ in range(3):
            h.tap("DEADBEEF")
        assert h.board.alarm and len(h.photos) == 1

    def two(h):
        h.tap("A1B2C3D4")
        h.tap("11223344")
        assert len(h.engine.sessions) == 2

    def expiry(h):
        entry(h)
        h.advance(61)
        assert not h.engine.sessions

    def matched(h):
        entry(h)
        assert h.tap("01020304", 1) == "ISS"
        h.lift()
        h.verdict("MATCHED")
        assert not h.board.alarm

    def late(h):
        entry(h)
        h.lift()
        h.advance(3)
        h.tap("01020304", 1)
        h.verdict("LATE_MATCH")
        assert not h.board.alarm

    def unscanned(h):
        entry(h)
        h.lift()
        h.advance(10)
        h.verdict("UNISSUED")
        assert h.board.alarm

    def denied(h):
        h.tap("11223344")
        assert h.tap("05060708", 1) == "PRM"
        h.lift(2)
        h.verdict("DENIED_REMOVAL")
        assert h.board.alarm

    def empty(h):
        h.lift()
        h.verdict("NO_SESSION")
        assert h.board.alarm

    def returned(h):
        matched(h)
        assert h.tap("01020304", 1) == "RET"
        h.engine.slot_change(1, "ABSENT", "PRESENT")
        h.pump()
        h.verdict("RETURN_MATCHED")

    def overdue(h):
        entry(h)
        h.tap("01020304", 1)
        h.advance(3601)
        with h.store.session() as s:
            assert s.scalar(select(Incident).where(Incident.kind == "OVERDUE"))

    def restart(h):
        entry(h)
        other = Engine(h.store, h.config, h.send, h.clock)
        assert len(other.sessions) == 1

    def provider_down(h):
        def down(*args):
            raise OSError("deliberate notifier outage")

        h.engine.alert = down
        unscanned(h)
        with h.store.session() as s:
            assert s.scalar(
                select(Reconciliation).where(Reconciliation.verdict == "UNISSUED")
            )

    for name, run in [
        ("valid badge entry", entry),
        ("unknown badge once: no saved photo", unknown),
        ("unknown badge three times: gate alarm and one photo", three),
        ("two simultaneous sessions", two),
        ("session TTL expires", expiry),
        ("issue then lift: MATCHED", matched),
        ("lift then permitted scan: LATE_MATCH", late),
        ("unscanned lift with worker: grace then alarm", unscanned),
        ("permission denied then lift: immediate alarm", denied),
        ("lift with nobody inside: immediate alarm", empty),
        ("return scan plus placement", returned),
        ("overdue warning", overdue),
        ("restart restores unexpired sessions", restart),
        ("notifier failure preserves alarm and verdict", provider_down),
    ]:
        case(name, run)

    def vision_case(h):
        import time

        src = SyntheticShelfSource()
        src.latest = src.grab()
        src.last_at = time.monotonic()
        v = Vision(src, h.store, h.config, h.engine)
        v.learn()
        for _ in range(5):
            v.process()
        src.states[0] = "occluded"
        src.latest = src.grab()
        for _ in range(5):
            v.process()
        assert v.states[1] == "OCCLUDED"
        report("PASS | operational | hand occlusion is not removal")
        src.states[0] = "present"
        src.moved = True
        src.latest = src.grab()
        for _ in range(5):
            v.process()
        assert v.rectification == "RECTIFIED" and v.states[1] == "PRESENT"
        report("PASS | operational | camera pose corrected with learned anchors")
        src.latest[:] = 0
        # Inject health time instead of sleeping to prove the cover threshold.
        now = time.monotonic()
        v.health.update(src.latest, now, now, {})
        assert v.health.update(src.latest, now + 2.1, now + 2.1, {}) == "COVERED"

    case("covered camera suspends observations", vision_case)


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as root:
        run_operational_scenarios(root)
