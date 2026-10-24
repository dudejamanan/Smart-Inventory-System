"""Authenticated REST, WebSocket, signed public media and Twilio callbacks."""

import asyncio
import hmac
import json
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.middleware.sessions import SessionMiddleware
from twilio.request_validator import RequestValidator
from app.config import Config, ROOT
from app.db.models import (
    Personnel,
    InventoryItem,
    ShelfSlot,
    Incident,
    SecurityEvent,
    FailedScan,
    CameraEvidence,
    Notification,
    Setting,
    Zone,
    PersonnelZone,
)
from app.db.store import row
from app.runtime import Runtime, SAFE_SETTINGS
from app.services.frames import marker, jpeg
from app.services.vision import crop
import cv2


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(StrictModel):
    password: str


class PersonInput(StrictModel):
    uid: str = Field(pattern=r"^(?:[0-9A-F]{8}|[0-9A-F]{14}|[0-9A-F]{20})$")
    name: str = Field(min_length=1, max_length=120)
    active: bool = True


class ItemInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    marker_id: int = Field(ge=0, le=29)
    notes: str = ""


class SlotInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    roi_x: float = Field(ge=0, lt=1)
    roi_y: float = Field(ge=0, lt=1)
    roi_w: float = Field(gt=0, le=1)
    roi_h: float = Field(gt=0, le=1)
    marker_id: int = Field(ge=0, le=29)
    item_id: int | None = None
    zone_id: int | None = None

    @model_validator(mode="after")
    def valid_roi(self):
        if self.roi_x + self.roi_w > 1 or self.roi_y + self.roi_h > 1:
            raise ValueError("ROI must fit in the frame")
        return self


class Calibration(StrictModel):
    slot_id: int
    roi_x: float = Field(ge=0, lt=1)
    roi_y: float = Field(ge=0, lt=1)
    roi_w: float = Field(gt=0, le=1)
    roi_h: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def valid_roi(self):
        if self.roi_x + self.roi_w > 1 or self.roi_y + self.roi_h > 1:
            raise ValueError("ROI outside frame")
        return self


class SlotId(StrictModel):
    slot_id: int


class IncidentEdit(StrictModel):
    keep: bool = False
    notes: str = ""


class SimInput(StrictModel):
    action: str
    uid: str = "A1B2C3D4"
    marker_id: int = Field(0, ge=0, le=29)
    state: str = "absent"


class ZoneInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)


class PermissionInput(StrictModel):
    zone_ids: list[int]


def create_app(config: Config | None = None, simulate=False, start_services=True):
    c = config or Config()
    if not simulate and (
        len(c.admin_password) < 12
        or len(c.cookie_secret) < 32
        or len(c.media_url_secret) < 32
    ):
        raise ValueError(
            "Set ADMIN_PASSWORD (12+ chars), COOKIE_SECRET and MEDIA_URL_SECRET (32+ chars) in .env"
        )
    # In simulation, local login is still required. Empty password is explicitly shown in setup.
    password = c.admin_password
    runtime = Runtime(c, simulate)

    @asynccontextmanager
    async def lifespan(app):
        runtime.loop = asyncio.get_running_loop()
        if start_services:
            runtime.start()
        yield
        runtime.close()

    app = FastAPI(title="Smart Warehouse", lifespan=lifespan)
    app.state.runtime = runtime
    app.add_middleware(
        SessionMiddleware,
        secret_key=c.cookie_secret or secrets.token_hex(32),
        same_site="strict",
        https_only=c.cookie_secure,
        max_age=8 * 3600,
    )
    attempts = {}

    @app.middleware("http")
    async def guard(request, call_next):
        path = request.url.path
        if path.startswith("/api/") and path != "/api/login":
            # SessionMiddleware is inside this middleware; decode in endpoint dependency below.
            pass
        if request.method in {"POST", "PUT", "DELETE", "PATCH"} and path.startswith(
            "/api/"
        ):
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc != request.headers.get("host"):
                return Response("Origin rejected", status_code=403)
            if (
                path != "/api/login"
                and request.headers.get("x-warehouse-request") != "1"
            ):
                return Response("Missing request header", status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    def admin(request: Request):
        if not request.session.get("admin"):
            raise HTTPException(401, "Sign in to the dashboard")

    @app.post("/api/login")
    def login(body: Login, request: Request):
        host = request.client.host if request.client else "local"
        recent = [t for t in attempts.get(host, []) if time.monotonic() - t < 60]
        attempts[host] = recent
        if len(recent) >= 10:
            raise HTTPException(429, "Wait one minute before retrying")
        if not hmac.compare_digest(body.password, password):
            recent.append(time.monotonic())
            raise HTTPException(401, "Incorrect password")
        request.session.clear()
        request.session["admin"] = True
        return {"ok": True}

    @app.post("/api/logout")
    def logout(request: Request):
        admin(request)
        request.session.clear()
        return {"ok": True}

    @app.get("/api/status")
    def status(request: Request):
        admin(request)
        return runtime.status()

    @app.get("/api/{resource}")
    def listing(resource: str, request: Request, limit: int = 100, offset: int = 0):
        admin(request)
        models = {
            "personnel": Personnel,
            "inventory": InventoryItem,
            "slots": ShelfSlot,
            "incidents": Incident,
            "events": SecurityEvent,
            "failed-scans": FailedScan,
            "zones": Zone,
        }
        model = models.get(resource)
        if model is None:
            raise HTTPException(404, "Unknown resource")
        with runtime.store.session() as s:
            return [
                row(v)
                for v in s.scalars(
                    select(model)
                    .order_by(model.id.desc())
                    .limit(max(1, min(limit, 500)))
                    .offset(max(0, offset))
                )
            ]

    def write_resource(resource, body, ident=None):
        models = {
            "personnel": (Personnel, PersonInput),
            "inventory": (InventoryItem, ItemInput),
            "slots": (ShelfSlot, SlotInput),
            "zones": (Zone, ZoneInput),
        }
        if resource not in models:
            raise HTTPException(404, "Unknown resource")
        model, schema = models[resource]
        try:
            data = schema.model_validate(body).model_dump()
        except Exception as exc:
            raise HTTPException(422, str(exc))
        try:
            with runtime.store.session() as s:
                obj = s.get(model, ident) if ident else model()
                if obj is None:
                    raise HTTPException(404, "Not found")
                for key, val in data.items():
                    setattr(obj, key, val)
                if model is ShelfSlot:
                    obj.empty_ref_path = None
                s.add(obj)
                s.flush()
                result = row(obj)
        except IntegrityError:
            raise HTTPException(409, "Duplicate value or invalid linked record")
        if resource == "personnel":
            runtime.engine.refresh()
        if resource in {"slots", "inventory"}:
            runtime.vision.reload()
        return result

    @app.post("/api/personnel/enrol")
    def enrol(request: Request):
        admin(request)
        runtime.engine.enrol = True
        runtime.engine.enrolled_uid = None
        return {
            "message": "Tap a card. It will remain unauthorized until you save the person."
        }

    @app.post("/api/{resource}")
    def create(resource: str, body: dict, request: Request):
        admin(request)
        return write_resource(resource, body)

    @app.put("/api/{resource}/{ident}")
    def update(resource: str, ident: int, body: dict, request: Request):
        admin(request)
        return write_resource(resource, body, ident)

    @app.delete("/api/{resource}/{ident}")
    def delete(resource: str, ident: int, request: Request):
        admin(request)
        model = {
            "personnel": Personnel,
            "inventory": InventoryItem,
            "slots": ShelfSlot,
            "zones": Zone,
        }.get(resource)
        if not model:
            raise HTTPException(404)
        try:
            with runtime.store.session() as s:
                obj = s.get(model, ident)
                if obj is None:
                    raise HTTPException(404)
                s.delete(obj)
        except IntegrityError:
            raise HTTPException(
                409, "Record is used by history. Deactivate personnel instead."
            )
        runtime.engine.refresh()
        if resource in {"slots", "inventory"}:
            runtime.vision.reload()
        return {"ok": True}

    @app.get("/api/personnel/{ident}/zones")
    def permissions(ident: int, request: Request):
        admin(request)
        with runtime.store.session() as s:
            if not s.get(Personnel, ident):
                raise HTTPException(404)
            return {
                "zone_ids": list(
                    s.scalars(
                        select(PersonnelZone.zone_id).where(
                            PersonnelZone.personnel_id == ident
                        )
                    )
                )
            }

    @app.put("/api/personnel/{ident}/zones")
    def set_permissions(ident: int, body: PermissionInput, request: Request):
        admin(request)
        with runtime.store.session() as s:
            if not s.get(Personnel, ident):
                raise HTTPException(404)
            if any(not s.get(Zone, z) for z in body.zone_ids):
                raise HTTPException(422, "Unknown zone")
            for permission in s.scalars(
                select(PersonnelZone).where(PersonnelZone.personnel_id == ident)
            ):
                s.delete(permission)
            s.flush()
            for z in set(body.zone_ids):
                s.add(PersonnelZone(personnel_id=ident, zone_id=z))
        return {"zone_ids": sorted(set(body.zone_ids))}

    @app.get("/api/incidents/{ident}")
    def detail(ident: int, request: Request):
        admin(request)
        with runtime.store.session() as s:
            i = s.get(Incident, ident)
            if not i:
                raise HTTPException(404)
            evidence = []
            for e in s.scalars(
                select(CameraEvidence).where(CameraEvidence.incident_id == ident)
            ):
                data = row(e)
                data["url"] = f"/api/evidence/{e.id}"
                evidence.append(data)
            return row(i) | {
                "evidence": evidence,
                "notifications": [
                    row(n)
                    for n in s.scalars(
                        select(Notification).where(Notification.incident_id == ident)
                    )
                ],
            }

    @app.post("/api/incidents/{ident}/ack")
    def ack(ident: int, request: Request):
        admin(request)
        if not runtime.engine.ack(ident):
            raise HTTPException(404)
        return {"ok": True}

    @app.post("/api/alarm/ack")
    def silence_alarm(request: Request):
        admin(request)
        runtime.serial.send({"t": "ACK"})
        return {"queued": True}

    @app.patch("/api/incidents/{ident}")
    def edit_incident(ident: int, body: IncidentEdit, request: Request):
        admin(request)
        with runtime.store.session() as s:
            i = s.get(Incident, ident)
            if not i:
                raise HTTPException(404)
            i.keep = body.keep
            i.notes = body.notes
            return row(i)

    @app.get("/api/evidence/{ident}")
    def evidence(ident: int, request: Request):
        admin(request)
        with runtime.store.session() as s:
            e = s.get(CameraEvidence, ident)
        if not e:
            raise HTTPException(404)
        path = Path(e.path).resolve()
        if not path.is_relative_to(c.data_dir.resolve()) or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    @app.get("/api/failed-scans/{ident}/photo")
    def failed_photo(ident: int, request: Request):
        admin(request)
        with runtime.store.session() as s:
            failed = s.get(FailedScan, ident)
        if not failed or not failed.photo_path:
            raise HTTPException(404, "No photo available")
        path = Path(failed.photo_path).resolve()
        if not path.is_relative_to(c.data_dir.resolve()) or not path.is_file():
            raise HTTPException(404, "Photo expired")
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/api/gate/latest.jpg")
    def latest(request: Request):
        admin(request)
        frame = runtime.gate.snapshot()
        if frame is None:
            raise HTTPException(503, "Gate camera offline")
        return Response(jpeg(frame), media_type="image/jpeg")

    @app.get("/api/shelf/stream")
    async def stream(request: Request):
        admin(request)

        async def generate():
            while not await request.is_disconnected():
                data = runtime.vision.annotated
                if data:
                    yield (
                        b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
                    )
                await asyncio.sleep(1 / c.process_fps)

        return StreamingResponse(
            generate(), media_type="multipart/x-mixed-replace; boundary=frame"
        )

    @app.get("/api/markers/{ident}.png")
    def marker_image(ident: int, request: Request):
        admin(request)
        if ident not in list(range(30)) + list(range(40, 50)):
            raise HTTPException(422, "Use item 0–29 or anchor 40–49")
        image = cv2.copyMakeBorder(
            marker(ident, 500), 50, 50, 50, 50, cv2.BORDER_CONSTANT, value=255
        )
        return Response(
            cv2.imencode(".png", image)[1].tobytes(), media_type="image/png"
        )

    @app.post("/api/test/{what}")
    def test_hardware(what: str, request: Request):
        admin(request)
        if what not in {"green", "red", "buzzer"}:
            raise HTTPException(422)
        runtime.serial.send({"t": "TEST", "what": what})
        return {"queued": True}

    @app.post("/api/calibration/slot")
    def calibration(body: Calibration, request: Request):
        admin(request)
        with runtime.store.session() as s:
            slot = s.get(ShelfSlot, body.slot_id)
            if not slot:
                raise HTTPException(404)
            for key, value in body.model_dump(exclude={"slot_id"}).items():
                setattr(slot, key, value)
            slot.empty_ref_path = None
        runtime.vision.debouncers.pop(body.slot_id, None)
        runtime.vision.reload()
        return {
            "ok": True,
            "message": "Capture a new empty reference after changing the ROI",
        }

    @app.post("/api/calibration/empty-reference")
    def empty_reference(body: SlotId, request: Request):
        admin(request)
        frame = runtime.shelf.snapshot()
        if frame is None:
            raise HTTPException(503, "Shelf camera offline")
        with runtime.store.session() as s:
            slot = s.get(ShelfSlot, body.slot_id)
            if not slot:
                raise HTTPException(404)
            path = c.data_dir / f"empty-{slot.id}-{secrets.token_hex(4)}.jpg"
            path.write_bytes(
                jpeg(crop(frame, (slot.roi_x, slot.roi_y, slot.roi_w, slot.roi_h)))
            )
            slot.empty_ref_path = str(path)
        runtime.vision.reload()
        return {"ok": True}

    # Settings routes registered before generic GET resource below via explicit ordering at end.
    @app.get("/api/settings")
    def settings(request: Request):
        admin(request)
        return {
            k: getattr(c, k)
            for k in sorted(SAFE_SETTINGS)
            if k != "shelf_stream_url" or not urlparse(c.shelf_stream_url).username
        }

    @app.put("/api/settings")
    def set_settings(body: dict, request: Request):
        admin(request)
        if set(body) - SAFE_SETTINGS:
            raise HTTPException(
                422, "Unknown or secret setting; edit .env for connection settings"
            )
        try:
            validated = Config(**(c.model_dump() | body))
            if (
                urlparse(validated.shelf_stream_url).username
                or urlparse(validated.shelf_stream_url).password
            ):
                if "shelf_stream_url" in body:
                    raise ValueError(
                        "Keep camera URL credentials only in .env; this setting cannot store credentials"
                    )
            if not 1 <= validated.debounce_n <= validated.debounce_m <= 30:
                raise ValueError("Require 1 <= N <= M <= 30")
            if validated.whatsapp_on not in {"third_failure", "every_failure"}:
                raise ValueError("Invalid WhatsApp policy")
        except Exception as exc:
            raise HTTPException(422, str(exc))
        with runtime.store.session() as s:
            for key in body:
                value = getattr(validated, key)
                setattr(c, key, value)
                s.merge(Setting(key=key, value=json.dumps(value)))
        runtime.vision.debouncers.clear()
        runtime.engine.sync()
        return settings(request)

    @app.post("/api/sim/control")
    def sim_control(body: SimInput, request: Request):
        admin(request)
        if not simulate:
            raise HTTPException(404)
        if body.action == "scan":
            from app.services.protocol import UID

            if not UID.fullmatch(body.uid):
                raise HTTPException(422, "Invalid UID")
            transport = runtime.serial.transport
            if transport:
                with transport.lock:
                    runtime.serial.board.scan(body.uid)
        elif body.action == "slot":
            if body.state not in {"present", "absent", "occluded"}:
                raise HTTPException(422)
            runtime.shelf.states[body.marker_id] = body.state
        elif body.action in {"covered", "offline", "moved"}:
            setattr(runtime.shelf, body.action, body.state == "on")
        elif body.action == "gate_offline":
            runtime.gate.offline = body.state == "on"
        elif body.action == "serial":
            runtime.serial.sim_disconnected = body.state == "off"
        else:
            raise HTTPException(422, "Unknown simulation action")
        return {"ok": True}

    @app.get("/media/{token}.jpg")
    def media(token: str):
        try:
            path = runtime.signer.verify(token)
        except ValueError:
            raise HTTPException(403, "Invalid or expired media URL")
        return FileResponse(path, media_type="image/jpeg")

    async def twilio_form(request):
        form = await request.form()
        data = dict(form)
        url = c.public_base_url.rstrip("/") + request.url.path
        if request.url.query:
            url += "?" + request.url.query
        if not c.twilio_auth_token or not RequestValidator(
            c.twilio_auth_token
        ).validate(url, data, request.headers.get("x-twilio-signature", "")):
            raise HTTPException(403, "Invalid Twilio signature")
        return data

    @app.post("/webhooks/twilio/status")
    async def twilio_status(request: Request):
        data = await twilio_form(request)
        with runtime.store.session() as s:
            for n in s.scalars(
                select(Notification).where(
                    Notification.provider_sid == data.get("MessageSid", "")
                )
            ):
                n.status = (
                    "FAILED_SESSION_EXPIRED"
                    if data.get("ErrorCode") == "63016"
                    else data.get("MessageStatus", "unknown")
                )
                n.error_code = data.get("ErrorCode")
        return Response("<Response/>", media_type="application/xml")

    @app.post("/webhooks/twilio/inbound")
    async def twilio_inbound(request: Request):
        data = await twilio_form(request)
        if data.get("From") == c.owner_whatsapp_to:
            with runtime.store.session() as s:
                s.merge(Setting(key="owner_last_inbound", value=str(time.time())))
        return Response("<Response/>", media_type="application/xml")

    @app.websocket("/ws")
    async def ws(socket: WebSocket):
        origin = socket.headers.get("origin")
        if not socket.session.get("admin") or (
            origin and urlparse(origin).netloc != socket.headers.get("host")
        ):
            await socket.close(code=1008)
            return
        await socket.accept()
        q = asyncio.Queue(maxsize=64)
        runtime.clients.add(q)
        try:
            while True:
                try:
                    message = await asyncio.wait_for(q.get(), timeout=2)
                except asyncio.TimeoutError:
                    message = {"type": "STATUS", "payload": runtime.status()}
                await socket.send_json(message)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            runtime.clients.discard(q)

    # Starlette resolves routes in declaration order; generic resource GET belongs last.
    generic = next(
        r
        for r in app.router.routes
        if getattr(r, "path", "") == "/api/{resource}"
        and "GET" in getattr(r, "methods", set())
    )
    app.router.routes.remove(generic)
    app.router.routes.append(generic)
    dist = ROOT / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="dashboard")
    return app
