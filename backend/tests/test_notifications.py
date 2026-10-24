from unittest.mock import Mock
import pytest
from app.services.notifier import (
    MediaSigner,
    TwilioNotifier,
    NotificationQueue,
    MockNotifier,
)
from app.config import Config
from app.db.store import Store
from app.db.models import Notification, Incident
from sqlalchemy import select


def test_sign_expiry_tamper_traversal(tmp_path):
    now = [100]
    p = tmp_path / "photo.jpg"
    p.write_bytes(b"jpeg")
    signer = MediaSigner(tmp_path, "secret", lambda: now[0])
    token = signer.sign(p)
    assert signer.verify(token) == p
    with pytest.raises(ValueError):
        signer.verify(token + "x")
    with pytest.raises(ValueError):
        signer.sign(tmp_path.parent / "escape.jpg")
    now[0] = 1001
    with pytest.raises(ValueError):
        signer.verify(token)


def test_twilio_sdk_mock():
    client = Mock()
    client.messages.create.return_value = Mock(sid="SM123", status="queued")
    c = Config(
        twilio_whatsapp_from="whatsapp:+1",
        owner_whatsapp_to="whatsapp:+2",
        public_base_url="https://example.test",
    )
    assert TwilioNotifier(c, client).send("alert", "https://example.test/p.jpg") == (
        "SM123",
        "queued",
    )
    assert client.messages.create.call_args.kwargs["media_url"] == [
        "https://example.test/p.jpg"
    ]


def test_retry_rate_limit_and_session_error(tmp_path):
    c = Config(data_dir=tmp_path)
    store = Store(c)
    with store.session() as s:
        i = Incident(kind="test", severity="CRITICAL")
        s.add(i)
        s.flush()
        ident = i.id
    provider = MockNotifier()
    q = NotificationQueue(store, c, MediaSigner(tmp_path, "test"), provider)
    q.enqueue(ident, "test", None, "gate", 1)
    q.enqueue(ident, "test", None, "gate", 1)
    q.process(q.q.get_nowait())
    with store.session() as s:
        ns = s.scalars(select(Notification)).all()
        assert [n.status for n in ns] == [
            "MOCK_SENT",
            "NO_PHOTO",
            "RATE_LIMITED",
            "RATE_LIMITED",
        ]

    class Expired(Exception):
        code = 63016

    provider.send = Mock(side_effect=Expired())
    q.deliver(ns[0].id, "test")
    with store.session() as s:
        assert s.get(Notification, ns[0].id).status == "FAILED_SESSION_EXPIRED"
    provider.send = Mock(side_effect=[OSError(), ("SMrecovered", "queued")])
    q.stop = Mock()
    q.stop.is_set.return_value = False
    q.stop.wait.return_value = False
    q.deliver(ns[0].id, "test")
    with store.session() as s:
        n = s.get(Notification, ns[0].id)
        assert n.attempts == 2 and n.status == "queued"
