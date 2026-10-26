"""Physical-workflow rules use injected time; no hardware results are implied."""

from unittest.mock import Mock
import pytest
from sqlalchemy import select
from app.config import Config
from app.db.store import Store
from app.db.models import Session, InventoryItem, Transaction, Reconciliation, Incident
from app.services.engine import Engine
from app.sim.arduino import SimulatedArduino
from app.services.offline import badge_entries
from app.services.protocol import fnv1a


class Clock:
    def __init__(self):
        self.now = 1000000.0

    def __call__(self):
        return self.now

    def advance(self, n):
        self.now += n


@pytest.fixture
def rules(tmp_path):
    c = Config(
        data_dir=tmp_path,
        twilio_account_sid="",
        twilio_auth_token="",
        session_ttl_min=1,
        overdue_check_s=1,
    )
    store = Store(c)
    store.seed()
    clock = Clock()
    sent = []
    engine = Engine(store, c, sent.append, clock)
    engine.evidence = Mock()
    engine.alert = Mock()
    engine.capture = Mock()
    yield engine, clock, sent, store
    store.engine.dispose()


def tap(e, uid, rd=0):
    seq = e.last_seq + 1
    e.authorize(dict(t="SCAN", uid=uid, seq=seq, rd=rd))
    result = e.pending_results[seq]["r"]
    e.handle(dict(t="FB", seq=seq, r=result, ms=2))
    return result


def verdicts(store):
    with store.session() as s:
        return [r.verdict for r in s.scalars(select(Reconciliation))]


def test_two_sessions_attribution_expiry_and_restart(rules):
    e, c, sent, store = rules
    assert tap(e, "A1B2C3D4") == "IN"
    assert tap(e, "11223344") == "IN"
    assert len(e.sessions) == 2
    assert tap(e, "05060708", 1) == "PRM"  # Meera L1 cannot issue multimeter L2
    c.advance(31)
    assert tap(e, "01020304", 1) == "NSS"  # two people, recent badge has expired
    restarted = Engine(store, e.c, sent.append, c)
    assert len(restarted.sessions) == 2
    c.advance(30)
    restarted.safety_tick()
    restarted.drain()
    assert not restarted.sessions and sent[-1] == {"t": "SYNC", "n": 0}
    with store.session() as s:
        assert all(v.end_reason == "EXPIRED" for v in s.scalars(select(Session)))


def test_issue_then_lift_consumes_only_one_token(rules):
    e, c, sent, store = rules
    tap(e, "A1B2C3D4")
    assert tap(e, "01020304", 1) == "ISS"
    e.slot_change(1, "PRESENT", "ABSENT")
    e.drain()
    assert verdicts(store) == ["MATCHED"]
    assert not any(m["t"] == "ALARM" for m in sent)
    with store.session() as s:
        item = s.get(InventoryItem, 1)
        assert item.status == "ISSUED" and item.holder_id == 1
        assert s.scalar(select(Transaction)).session_id is not None


def test_lift_then_late_scan_cancels_prewarning(rules):
    e, c, sent, store = rules
    tap(e, "A1B2C3D4")
    e.slot_change(1, "PRESENT", "ABSENT")
    assert sent[-1] == {"t": "PW", "on": 1, "s": 10}
    c.advance(5)
    assert tap(e, "01020304", 1) == "ISS"
    assert {"t": "PW", "on": 0} in sent and verdicts(store) == ["LATE_MATCH"]
    c.advance(10)
    e.safety_tick()
    e.drain()
    assert not any(m["t"] == "ALARM" for m in sent)


@pytest.mark.parametrize(
    "mode,expected",
    [("grace", "UNISSUED"), ("denied", "DENIED_REMOVAL"), ("empty", "NO_SESSION")],
)
def test_illegal_removals_alarm_with_evidence(rules, mode, expected):
    e, c, sent, store = rules
    if mode != "empty":
        tap(e, "11223344")
    if mode == "denied":
        assert tap(e, "05060708", 1) == "PRM"
    sid = 2 if mode == "denied" else 1
    e.slot_change(sid, "PRESENT", "ABSENT")
    if mode == "grace":
        c.advance(10)
        e.safety_tick()
    assert {"t": "ALARM", "on": 1, "why": "SHELF_BREACH"} in sent
    e.drain()
    assert expected in verdicts(store)
    assert e.evidence.called and e.alert.call_args.args[3] == "shelf"


def test_multiple_pending_removals_never_extend_other_deadline(rules):
    e, c, sent, store = rules
    tap(e, "A1B2C3D4")
    e.slot_change(1, "PRESENT", "ABSENT")
    c.advance(4)
    e.slot_change(2, "PRESENT", "ABSENT")
    assert [m for m in sent if m["t"] == "PW"] == [{"t": "PW", "on": 1, "s": 10}]
    tap(e, "01020304", 1)
    c.advance(10)
    e.safety_tick()
    e.drain()
    assert verdicts(store) == ["LATE_MATCH", "UNISSUED"]


def test_return_other_return_unscanned_and_not_observed(rules):
    e, c, sent, store = rules
    tap(e, "A1B2C3D4")
    tap(e, "01020304", 1)
    e.slot_change(1, "PRESENT", "ABSENT")
    e.drain()
    tap(e, "11223344")
    assert tap(e, "01020304", 1) == "RET"
    e.slot_change(1, "ABSENT", "PRESENT")
    e.drain()
    with store.session() as s:
        assert (
            s.scalars(select(Transaction).order_by(Transaction.id.desc())).first().kind
            == "RETURN_OTHER"
        )
    assert verdicts(store)[-1] == "RETURN_MATCHED"
    tap(e, "01020304", 1)
    e.slot_change(1, "PRESENT", "ABSENT")
    e.drain()
    e.slot_change(1, "ABSENT", "PRESENT")
    c.advance(20)
    e.safety_tick()
    e.drain()
    assert verdicts(store)[-1] == "RETURN_UNSCANNED"
    # Return while the slot is absent needs physical placement within 60 seconds.
    e.reconcile.present[1] = "ABSENT"
    assert tap(e, "01020304", 1) == "RET"
    c.advance(60)
    e.safety_tick()
    e.drain()
    assert verdicts(store)[-1] == "RETURN_NOT_OBSERVED"


def test_overdue_once_and_cache_contains_real_levels_items(rules):
    e, c, sent, store = rules
    tap(e, "A1B2C3D4")
    tap(e, "01020304", 1)
    c.advance(3601)
    e.safety_tick()
    e.drain()
    e.safety_tick()
    e.drain()
    with store.session() as s:
        assert (
            len(list(s.scalars(select(Incident).where(Incident.kind == "OVERDUE"))))
            == 1
        )
    entries = badge_entries(e)
    assert (fnv1a("A1B2C3D4"), 2, False) in entries
    assert (fnv1a("090A0B0C"), 3, True) in entries


def test_db_camera_provider_failure_does_not_block_timer_or_auth(rules, monkeypatch):
    e, c, sent, store = rules
    tap(e, "A1B2C3D4")
    monkeypatch.setattr(store, "session", Mock(side_effect=OSError("database down")))
    e.evidence = Mock(side_effect=OSError("camera down"))
    e.alert = Mock(side_effect=OSError("provider down"))
    e.slot_change(1, "PRESENT", "ABSENT")
    c.advance(10)
    e.safety_tick()
    assert sent[-1] in [
        {"t": "PW", "on": 0},
        {"t": "ALARM", "on": 1, "why": "SHELF_BREACH"},
    ]
    assert {"t": "ALARM", "on": 1, "why": "SHELF_BREACH"} in sent
    e.authorize(dict(t="SCAN", uid="11223344", seq=99, rd=0))
    assert sent[-1]["r"] == "IN"


def test_gate_photos_only_third_failure_item_reader_never_gate_alarm(rules):
    e, c, sent, store = rules
    b = SimulatedArduino(e.c, clock=c, readers=2)
    b.drain()

    def scan(uid, rd):
        b.receive({"t": "HB", "n": len(e.sessions)})
        b.scan(uid, rd)
        while b.events:
            m = b.events.popleft()
            before = len(sent)
            e.authorize(m)
            for response in sent[before:]:
                b.receive(response)
            e.handle(m)
        c.advance(1.6)

    scan("DEADBEEF", 0)
    scan("DEADBEEF", 0)
    e.capture.assert_not_called()
    scan("DEADBEEF", 0)
    assert e.capture.call_count == 1
    b.stop_alarm("ACK")
    b.drain()
    e.capture.reset_mock()
    for _ in range(3):
        scan("DEADBEEF", 1)
    e.capture.assert_not_called()
    assert b.failures == 0


def test_wrong_reader_and_enrolment_have_no_side_effects(rules):
    e, c, sent, store = rules
    assert tap(e, "01020304", 0) == "PRM"
    assert tap(e, "A1B2C3D4", 1) == "PRM"
    e.enrol = True
    assert tap(e, "A1B2C3D4") == "PRM" and not e.sessions
    assert e.enrolled_uid == "A1B2C3D4"
