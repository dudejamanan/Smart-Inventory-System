"""Isolated notification queue; failures never propagate to the alarm path."""

import base64
import hashlib
import hmac
import json
import logging
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from twilio.rest import Client
from twilio.http.http_client import TwilioHttpClient
from app.db.models import Notification, Setting
from app.services.frames import jpeg
import cv2
import httpx

log = logging.getLogger(__name__)


class MediaSigner:
    def __init__(self, root: Path, secret: str, clock=time.time):
        self.root = root.resolve()
        self.secret = secret.encode()
        self.clock = clock

    def sign(self, path: Path, ttl=900):
        relative = path.resolve().relative_to(self.root).as_posix()
        payload = (
            base64.urlsafe_b64encode(
                json.dumps(
                    [relative, int(self.clock() + ttl)], separators=(",", ":")
                ).encode()
            )
            .decode()
            .rstrip("=")
        )
        return (
            payload
            + "."
            + hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()
        )

    def verify(self, token: str):
        try:
            payload, sig = token.split(".")
            expected = hmac.new(
                self.secret, payload.encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(sig, expected):
                raise ValueError("Invalid signature")
            relative, expires = json.loads(
                base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
            )
            if expires <= self.clock():
                raise ValueError("Expired media URL")
            path = (self.root / relative).resolve()
            path.relative_to(self.root)
            if path.suffix.lower() != ".jpg" or not path.is_file():
                raise ValueError("Not a JPEG file")
            return path
        except Exception as exc:
            raise ValueError("Invalid or expired media token") from exc


class Notifier(Protocol):
    def send(self, body: str, media_url: str | None = None): ...


class MockNotifier:
    def __init__(self):
        self.messages = []

    def send(self, body, media_url=None):
        self.messages.append({"body": body, "media_url": media_url})
        return "MOCK" + uuid.uuid4().hex, "MOCK_SENT"


class TwilioNotifier:
    def __init__(self, c, client=None):
        self.c = c
        self.client = client or Client(
            c.twilio_account_sid,
            c.twilio_auth_token,
            http_client=TwilioHttpClient(timeout=5),
        )

    def send(self, body, media_url=None):
        kw = {
            "from_": self.c.twilio_whatsapp_from,
            "to": self.c.owner_whatsapp_to,
            "body": body,
            "status_callback": self.c.public_base_url.rstrip("/")
            + "/webhooks/twilio/status",
        }
        if media_url:
            kw["media_url"] = [media_url]
        msg = self.client.messages.create(**kw)
        return msg.sid, msg.status


class TelegramNotifier:
    """Direct multipart upload: no public camera URL or tunnel is needed."""

    def __init__(self, c, client=None):
        self.c = c
        logging.getLogger("httpx").setLevel(logging.WARNING)  # bot token is in the URL
        self.client = client or httpx.Client(timeout=5)

    def send(self, body, media_url=None):
        endpoint = "sendPhoto" if media_url else "sendMessage"
        url = f"https://api.telegram.org/bot{self.c.telegram_bot_token}/{endpoint}"
        if media_url:
            with Path(media_url).open("rb") as photo:
                response = self.client.post(
                    url,
                    data={"chat_id": self.c.telegram_chat_id, "caption": body[:1024]},
                    files={"photo": ("evidence.jpg", photo, "image/jpeg")},
                )
        else:
            response = self.client.post(
                url, json={"chat_id": self.c.telegram_chat_id, "text": body}
            )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise OSError("Telegram rejected request")
        return str(data["result"]["message_id"]), "SENT"


def prepare_media(path: Path, root: Path):
    frame = cv2.imread(str(path))
    if frame is None:
        raise OSError("Cannot read notification photo")
    h, w = frame.shape[:2]
    frame = cv2.resize(
        frame, (max(1, int(w * min(1, 1280 / w))), max(1, int(h * min(1, 1280 / w))))
    )
    for quality in [85, 70, 50, 30]:
        data = jpeg(frame, quality)
        if len(data) <= 1_000_000:
            break
    else:
        raise OSError("Photo cannot fit 1 MB limit")
    target = root / "outgoing" / f"{uuid.uuid4().hex}.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


class NotificationQueue:
    def __init__(self, store, c, signer, provider=None, clock=time.time):
        self.store, self.c, self.signer = store, c, signer
        self.provider = provider or (
            TwilioNotifier(c)
            if c.twilio_account_sid and c.twilio_auth_token
            else MockNotifier()
        )
        self.clock = clock
        self.q = queue.Queue(maxsize=256)
        self.stop = threading.Event()
        self.last_kind = {}
        self.lock = threading.Lock()
        self.thread = None
        self.photo = lambda source, seq: None
        self.last_send = 0.0
        self.configuration_error = None
        if (
            not provider
            and any(
                [
                    c.twilio_account_sid,
                    c.twilio_auth_token,
                    c.twilio_whatsapp_from,
                    c.owner_whatsapp_to,
                    c.public_base_url,
                ]
            )
            and not all(
                [
                    c.twilio_account_sid,
                    c.twilio_auth_token,
                    c.twilio_whatsapp_from,
                    c.owner_whatsapp_to,
                    c.public_base_url.startswith("https://"),
                ]
            )
        ):
            self.configuration_error = "Incomplete WhatsApp setup: SID, token, sender, owner and public HTTPS URL are required"
        self.enabled = "whatsapp" in c.notify_channels.split(",") or isinstance(
            self.provider, TelegramNotifier
        )
        if not self.enabled:
            self.configuration_error = None
        if isinstance(self.provider, TelegramNotifier) and not (
            c.telegram_bot_token and c.telegram_chat_id
        ):
            self.configuration_error = (
                "Telegram needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"
            )

    def enqueue(self, incident, kind, uid, source, seq):
        with self.lock:
            limited = self.clock() - self.last_kind.get(kind, -1e20) < 20
            if not limited:
                self.last_kind[kind] = self.clock()
        with self.store.session() as s:
            rows = []
            for part in ["text", "media"]:
                n = Notification(
                    channel="telegram"
                    if isinstance(self.provider, TelegramNotifier)
                    else "whatsapp",
                    incident_id=incident,
                    to=(
                        self.c.telegram_chat_id
                        if isinstance(self.provider, TelegramNotifier)
                        else self.c.owner_whatsapp_to
                    )
                    or "mock-owner",
                    kind=part,
                    status="RATE_LIMITED" if limited else "QUEUED",
                )
                s.add(n)
                s.flush()
                rows.append(n.id)
        if not limited:
            try:
                self.q.put_nowait((incident, kind, uid, source, seq, rows))
            except queue.Full:
                for ident in rows:
                    self.update(ident, status="FAILED_QUEUE_FULL")

    def update(self, ident, **kw):
        with self.store.session() as s:
            n = s.get(Notification, ident)
            for key, val in kw.items():
                setattr(n, key, val)

    def deliver(self, ident, body, url=None):
        for attempt in range(1, 4):
            if self.stop.is_set():
                self.update(ident, status="CANCELLED_SHUTDOWN")
                return
            self.update(ident, attempts=attempt, status="SENDING")
            try:
                if isinstance(self.provider, TwilioNotifier):
                    # Sandbox allows one message per three seconds, across kinds.
                    remaining = 3.1 - (time.monotonic() - self.last_send)
                    if remaining > 0 and self.stop.wait(remaining):
                        self.update(ident, status="CANCELLED_SHUTDOWN")
                        return
                    self.last_send = time.monotonic()
                sid, status = self.provider.send(body, url)
                self.update(ident, provider_sid=sid, status=status)
                return
            except Exception as exc:
                code = str(getattr(exc, "code", "") or "")
                if code == "63016":
                    self.update(ident, status="FAILED_SESSION_EXPIRED", error_code=code)
                    return
                log.warning(
                    "Notification attempt %s failed: %s", attempt, type(exc).__name__
                )
                self.update(
                    ident,
                    status="FAILED" if attempt == 3 else "RETRYING",
                    error_code=code or type(exc).__name__,
                )
                if attempt < 3 and self.stop.wait(2 ** (attempt - 1)):
                    self.update(ident, status="CANCELLED_SHUTDOWN")
                    return

    def process(self, job):
        incident, kind, uid, source, seq, rows = job
        if not self.enabled:
            for ident in rows:
                self.update(ident, status="DISABLED")
            return
        if self.configuration_error:
            for ident in rows:
                self.update(
                    ident, status="FAILED_CONFIGURATION", error_code="SETUP_INCOMPLETE"
                )
            return
        if self.stop.is_set():
            for ident in rows:
                self.update(ident, status="CANCELLED_SHUTDOWN")
            return
        if isinstance(self.provider, TwilioNotifier) and not self.session_remaining():
            for ident in rows:
                self.update(ident, status="FAILED_SESSION_EXPIRED", error_code="63016")
            return
        body = f"{kind} | {datetime.now(timezone.utc).isoformat()} | UID {uid or 'none'} | {self.c.public_base_url}/#incidents/{incident}"
        self.deliver(rows[0], body)
        try:
            path = self.photo(source, seq)
            if not path:
                self.update(rows[1], status="NO_PHOTO")
                return
            photo = prepare_media(Path(path), self.c.data_dir)
            if isinstance(self.provider, TelegramNotifier):
                self.deliver(rows[1], body, str(photo))
                return
            url = (
                self.c.public_base_url.rstrip("/")
                + "/media/"
                + self.signer.sign(photo)
                + ".jpg"
            )
            self.deliver(rows[1], body, url)
        except Exception:
            log.exception("Media preparation failed")
            self.update(rows[1], status="FAILED_MEDIA")

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while not self.stop.is_set() or not self.q.empty():
            try:
                job = self.q.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self.process(job)
            except Exception:
                log.exception("Notification job failed")
            finally:
                self.q.task_done()

    def session_remaining(self):
        with self.store.session() as s:
            setting = s.get(Setting, "owner_last_inbound")
            return (
                max(0, 86400 - (self.clock() - float(setting.value))) if setting else 0
            )

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(12)
