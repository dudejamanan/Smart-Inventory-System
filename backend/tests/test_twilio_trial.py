from unittest.mock import Mock
from sqlalchemy import select
from app.config import Config
from app.db.store import Store
from app.db.models import Incident, Notification
from app.services.notifier import (
    MediaSigner,
    NotificationQueue,
    TwilioNotifier,
    MockNotifier,
)


def incident(store):
    with store.session() as s:
        row = Incident(kind="TEST", severity="WARNING")
        s.add(row)
        s.flush()
        return row.id


def test_trial_restriction_is_visible_and_does_not_call_provider(tmp_path):
    c = Config(data_dir=tmp_path, twilio_template_only=True)
    store = Store(c)
    sdk = Mock()
    provider = TwilioNotifier(c, client=sdk)
    q = NotificationQueue(store, c, MediaSigner(tmp_path, "test"), provider)
    q.enqueue(incident(store), "TEST", None, "gate", 1)
    q.process(q.q.get_nowait())
    sdk.messages.create.assert_not_called()
    assert "predefined templates" in q.configuration_error
    with store.session() as s:
        rows = list(s.scalars(select(Notification)))
        assert all(
            n.status == "BLOCKED_TRIAL_RESTRICTION" and n.error_code == "21654"
            for n in rows
        )
    store.engine.dispose()


def test_content_sid_required_is_permanent_not_three_retries(tmp_path):
    c = Config(data_dir=tmp_path, twilio_template_only=False)
    store = Store(c)
    provider = MockNotifier()

    class TemplateRequired(Exception):
        code = 21654

    provider.send = Mock(side_effect=TemplateRequired())
    q = NotificationQueue(store, c, MediaSigner(tmp_path, "test"), provider)
    q.enqueue(incident(store), "TEST", None, "gate", 1)
    with store.session() as s:
        ident = s.scalar(select(Notification.id))
    q.deliver(ident, "test")
    provider.send.assert_called_once()
    with store.session() as s:
        n = s.get(Notification, ident)
        assert n.status == "FAILED_TEMPLATE_REQUIRED" and n.attempts == 1
    store.engine.dispose()
