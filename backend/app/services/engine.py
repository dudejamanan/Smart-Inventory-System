"""Rules engine: cache-first authorization; database/evidence failures cannot block AUTH."""

import json
import logging
import threading
import time
from sqlalchemy import select
from app.db.models import Personnel, Session, SecurityEvent, Incident, FailedScan

log = logging.getLogger(__name__)


class Engine:
    def __init__(self, store, config, send):
        self.store, self.c, self.send = store, config, send
        self.lock = threading.RLock()
        self.whitelist = {}
        self.current = None
        self.fail_counter = 0
        self.fail_started = 0.0
        self.alarm = False
        self.last_uid = None
        self.last_seq = 0
        self.enrol = False
        self.enrolled_uid = None
        self.capture = lambda *args: None
        self.alert = lambda *args: None
        self.evidence = lambda *args: None
        self.publish = lambda *args: None
        self.refresh()
        with store.session() as s:
            opened = s.scalar(select(Session).where(Session.end_ts.is_(None)))
            if opened:
                p = s.get(Personnel, opened.personnel_id)
                self.current = {
                    "id": opened.id,
                    "personnel_id": p.id,
                    "uid": p.uid,
                    "name": p.name,
                }

    def refresh(self):
        with self.store.session() as s:
            people = s.scalars(
                select(Personnel).where(Personnel.active.is_(True))
            ).all()
            with self.lock:
                self.whitelist = {p.uid: {"id": p.id, "name": p.name} for p in people}

    def sync(self):
        self.send(
            {
                "t": "CFG",
                "fail_limit": self.c.fail_limit,
                "window_s": self.c.fail_window_s,
                "alarm_s": self.c.alarm_s,
            }
        )
        m = {"t": "SYNC", "state": "OUT"}
        if self.current:
            m.update(state="IN", uid=self.current["uid"])
        self.send(m)

    def event(self, kind, payload, severity="INFO"):
        with self.store.session() as s:
            s.add(
                SecurityEvent(
                    type=kind, severity=severity, payload_json=json.dumps(payload)
                )
            )
        self.publish(kind, payload)

    def incident(self, kind, severity="WARNING", **kw):
        with self.store.session() as s:
            i = Incident(kind=kind, severity=severity, **kw)
            s.add(i)
            s.flush()
            ident = i.id
        self.publish("INCIDENT", {"id": ident, "kind": kind})
        return ident

    def authorize(self, m):
        """Called directly on serial reader before queuing durable processing."""
        if m["t"] == "SCAN":
            with self.lock:
                ok = int(m["uid"] in self.whitelist)
            self.send({"t": "AUTH", "seq": m["seq"], "ok": ok})
            self.last_uid, self.last_seq = m["uid"], m["seq"]
            if self.enrol:
                self.enrolled_uid = m["uid"]
                self.enrol = False
            try:
                self.capture(m["uid"], m["seq"], bool(ok))
            except Exception:
                log.exception("Capture scheduling failed")

    def handle(self, m):
        with self.lock:
            t = m["t"]
            if t == "BOOT":
                self.sync()
            elif t == "SESSION":
                with self.store.session() as s:
                    if m["state"] == "IN" and not self.current:
                        p = s.scalar(select(Personnel).where(Personnel.uid == m["uid"]))
                        if p:
                            session = Session(personnel_id=p.id)
                            s.add(session)
                            s.flush()
                            self.current = {
                                "id": session.id,
                                "personnel_id": p.id,
                                "uid": p.uid,
                                "name": p.name,
                            }
                    elif m["state"] == "OUT" and self.current:
                        session = s.get(Session, self.current["id"])
                        session.end_ts = time.time()
                        self.current = None
                self.fail_counter = 0
            elif t == "FAIL":
                self.fail_counter = m["n"]
                if m["n"] == 1:
                    self.fail_started = time.monotonic()
                with self.store.session() as s:
                    s.add(FailedScan(uid=m["uid"], counter=m["n"]))
                if self.c.whatsapp_on == "every_failure":
                    ident = self.incident("GATE_FAILURE", uid=m["uid"])
                    self.alert(ident, "GATE_FAILURE", m["uid"], "gate", self.last_seq)
            elif t == "ALARM":
                self.alarm = True
                if m["why"] != "SHELF_BREACH":
                    ident = self.incident(m["why"], "CRITICAL", uid=self.last_uid)
                    with self.store.session() as s:
                        fails = s.scalars(
                            select(FailedScan)
                            .where(FailedScan.incident_id.is_(None))
                            .order_by(FailedScan.id.desc())
                            .limit(self.c.fail_limit)
                        ).all()
                        for f in fails:
                            f.incident_id = ident
                    self.alert(ident, m["why"], self.last_uid, "gate", self.last_seq)
                self.fail_counter = 0
            elif t == "ALARM_OFF":
                self.alarm = False
            elif t == "BUSY":
                self.fail_counter = 0
            self.event(t, m)

    def slot_change(self, slot_id, old, new):
        with self.lock:
            worker = self.current.copy() if self.current else None
            # Send before any database/evidence work. UNO decides whether to sound.
            if new == "ABSENT":
                self.send({"t": "REMOVAL", "slot": slot_id})
            payload = {"slot_id": slot_id, "old": old, "state": new, "worker": worker}
            self.event("SLOT_STATE", payload)
            if new == "ABSENT":
                if worker:
                    self.event("ITEM_REMOVED", payload)
                else:
                    ident = self.incident("SHELF_BREACH", "CRITICAL", slot_id=slot_id)
                    self.evidence(ident)
                    self.alert(ident, "SHELF_BREACH", None, "shelf", None)
            elif new == "PRESENT" and old in {"ABSENT", "OCCLUDED"} and not worker:
                self.incident("ITEM_RETURNED", slot_id=slot_id)

    def occluded(self, slot_id):
        if not self.current:
            self.incident("SLOT_OCCLUDED", slot_id=slot_id)

    def camera_health(self, camera, status, detail=""):
        from app.db.models import CameraHealthLog

        with self.store.session() as s:
            s.add(CameraHealthLog(camera=camera, status=status, detail=detail))
        self.event(
            "CAMERA_HEALTH",
            {"camera": camera, "status": status, "detail": detail},
            "WARNING" if status != "OK" else "INFO",
        )
        if status != "OK":
            self.incident("CAMERA_" + status, notes=camera + ": " + detail)

    def ack(self, ident):
        self.send({"t": "ACK"})
        with self.store.session() as s:
            i = s.get(Incident, ident)
            if not i:
                return False
            i.status = "ACKNOWLEDGED"
            i.ack_ts = time.time()
        self.event("ACK", {"incident_id": ident})
        return True
