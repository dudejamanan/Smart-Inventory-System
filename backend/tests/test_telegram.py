import httpx
from sqlalchemy import select
from app.config import Config
from app.db.store import Store
from app.db.models import Incident, Notification
from app.services.notifier import TelegramNotifier, NotificationQueue, MediaSigner


def test_telegram_multipart_retry_and_per_kind_limit(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 12}})

    c = Config(
        data_dir=tmp_path,
        telegram_bot_token="test-only",
        telegram_chat_id="123",
        notify_channels="telegram",
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    notifier = TelegramNotifier(c, client)
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"JPEG test bytes")
    store = Store(c)
    with store.session() as s:
        i = Incident(kind="TEST", severity="WARNING")
        s.add(i)
        s.flush()
        ident = i.id
    q = NotificationQueue(store, c, MediaSigner(tmp_path, "test"), provider=notifier)
    from unittest.mock import Mock

    q.stop = Mock()
    q.stop.is_set.return_value = False
    q.stop.wait.return_value = False
    q.enqueue(ident, "TEST", None, "shelf", None)
    q.enqueue(ident, "TEST", None, "shelf", None)
    with store.session() as s:
        rows = list(s.scalars(select(Notification)))
    q.deliver(rows[0].id, "text")
    q.deliver(rows[1].id, "photo", str(photo))
    assert requests[-1].url.path.endswith("/sendPhoto")
    assert b"JPEG test bytes" in requests[-1].content
    with store.session() as s:
        assert s.get(Notification, rows[0].id).attempts == 2
        assert s.get(Notification, rows[2].id).status == "RATE_LIMITED"
        assert all(n.channel == "telegram" for n in s.scalars(select(Notification)))
    client.close()
    store.engine.dispose()
