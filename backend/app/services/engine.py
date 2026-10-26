"""Operational two-reader policy: RAM decisions, isolated timers, queued durability."""

import json
import logging
import queue
import threading
import time
import uuid
from sqlalchemy import select
from app.services.legacy_engine import Engine as LegacyEngine
from app.services.reconcile import Reconciler
from app.db.models import (
    Personnel,
    Session,
    InventoryItem,
    ShelfSlot,
    PersonnelZone,
    Transaction,
    Reconciliation,
    Incident,
)

log = logging.getLogger(__name__)


class Engine(LegacyEngine):
    def __init__(self, store, config, send, clock=time.time):
        self.clock = clock
        self.sessions = {}
        self.items = {}
        self.slots = {}
        self.jobs = queue.Queue(maxsize=4096)
        self.drain_lock = threading.RLock()
        self.retry_job = None
        self.last_shelf_alarm = -1e20
        self.persistence_error = None
        self.recent = None
        self.confirmed = {}
        self.overdue = set()
        self.last_overdue = 0
        self.shelf_health = "UNKNOWN"
        self.monitoring_paused = False
        self.removal_seen = lambda slot_id: None
        self.evidence_for_slot = lambda ident, slot_id: self.evidence(ident)
        super().__init__(store, config, send)
        self.current = None
        now = self.clock()
        with store.session() as s:
            for opened in s.scalars(select(Session).where(Session.end_ts.is_(None))):
                expiry = (
                    opened.expires_ts or opened.start_ts + config.session_ttl_min * 60
                )
                if expiry <= now or opened.personnel_id not in {
                    p["id"] for p in self.whitelist.values()
                }:
                    opened.end_ts, opened.end_reason = now, "EXPIRED"
                else:
                    p = s.get(Personnel, opened.personnel_id)
                    self.sessions[p.uid] = dict(
                        id=opened.id,
                        personnel_id=p.id,
                        uid=p.uid,
                        name=p.name,
                        expires_ts=expiry,
                    )
        self._current()
        self.reconcile = Reconciler(config, send, self.enqueue, clock)

    def _current(self):
        self.current = next(iter(self.sessions.values()), None)

    def refresh(self):
        # Read first, publish atomically. No DB work while holding auth_lock.
        self.drain()
        with self.auth_lock:
            previous = {
                uid: (item.get("status"), item.get("holder_id"), item.get("due_ts"))
                for uid, item in self.items.items()
            }
        with self.store.session() as s:
            people = {
                p.uid: dict(id=p.id, name=p.name, level=p.level)
                for p in s.scalars(select(Personnel).where(Personnel.active.is_(True)))
            }
            items = {
                i.tag_uid: dict(
                    id=i.id,
                    name=i.name,
                    min_level=i.min_level,
                    loan_minutes=i.loan_minutes,
                    status=i.status,
                    holder_id=i.holder_id,
                    due_ts=i.due_ts,
                )
                for i in s.scalars(select(InventoryItem))
                if i.tag_uid
            }
            slots = {
                v.id: dict(id=v.id, item_id=v.item_id, zone_id=v.zone_id)
                for v in s.scalars(select(ShelfSlot))
            }
            zones = {
                (v.personnel_id, v.zone_id) for v in s.scalars(select(PersonnelZone))
            }
        with self.auth_lock:
            for uid, item in items.items():
                current = self.items.get(uid)
                if current and (
                    current.get("status"),
                    current.get("holder_id"),
                    current.get("due_ts"),
                ) != previous.get(uid):
                    item.update(
                        {k: current[k] for k in ["status", "holder_id", "due_ts"]}
                    )
            self.whitelist, self.items, self.slots, self.zones = (
                people,
                items,
                slots,
                zones,
            )
            for uid in list(self.sessions):
                if uid not in people:
                    self.enqueue(
                        "close", self.sessions.pop(uid) | {"reason": "REVOKED"}
                    )
            self._current()
        self.whitelist_changed()

    def enqueue(self, kind, payload):
        if kind == "reconcile":
            payload["token"] = uuid.uuid4().hex
            if payload["alarm"]:
                self.alarm = True
                self.last_shelf_alarm = self.clock()
                for item in self.items.values():
                    if item["id"] == payload["item_id"] and item["status"] != "ISSUED":
                        item["status"] = "MISSING"
        try:
            self.jobs.put_nowait((kind, payload))
        except queue.Full:
            self.send({"t": "ALARM", "on": 1, "why": "PC_CMD"})
            log.critical(
                "Rules persistence queue full; fail closed and retain controller alarm"
            )

    def expire(self):
        now = self.clock()
        changed = False
        for uid, session in list(self.sessions.items()):
            if session["expires_ts"] <= now:
                self.sessions.pop(uid)
                self.enqueue("close", session | {"reason": "EXPIRED"})
                changed = True
        if changed:
            self._current()
            self.send({"t": "SYNC", "n": len(self.sessions)})

    def sync(self):
        self.send(
            {
                "t": "CFG",
                "fail_limit": self.c.fail_limit,
                "window_s": self.c.fail_window_s,
                "alarm_s": self.c.alarm_s,
            }
        )
        self.send({"t": "SYNC", "n": len(self.sessions)})

    def authorize(self, m):
        t = m["t"]
        if t == "FB":
            self.confirm(m)
            return
        if t == "ALARM" and m["why"] == "GATE_3_FAIL":
            # Capture is scheduled only at the threshold, before durable work.
            try:
                self.capture(self.last_uid or "UNKNOWN", self.last_seq, False)
            except Exception:
                log.exception("Gate photo scheduling failed; board alarm continues")
            return
        if t != "SCAN":
            return
        uid, seq, rd = m["uid"], m["seq"], m.get("rd", 0)
        with self.auth_lock:
            self.expire()
            self.last_uid, self.last_seq = uid, seq
            if self.enrol:
                self.enrolled_uid, self.enrol = uid, False
                result, person, item = "PRM", None, None
            else:
                person, item = self.whitelist.get(uid), self.items.get(uid)
                result = "DEN"
                if self.firmware_compatible:
                    if rd == 0 and person:
                        result = (
                            "OUT"
                            if uid in self.sessions
                            else "IN"
                            if len(self.sessions) < self.c.max_sessions
                            else "PRM"
                        )
                    elif rd == 1 and item:
                        active = (
                            self.sessions.get(self.recent[0])
                            if self.recent
                            and self.clock() - self.recent[1]
                            <= self.c.attribution_window_s
                            else None
                        )
                        active = active or (
                            next(iter(self.sessions.values()))
                            if len(self.sessions) == 1
                            else None
                        )
                        person = self.whitelist.get(active["uid"]) if active else None
                        allowed = bool(person and person["level"] >= item["min_level"])
                        if self.c.zones_enabled and person:
                            required = {
                                s["zone_id"]
                                for s in self.slots.values()
                                if s["item_id"] == item["id"] and s["zone_id"]
                            }
                            allowed = allowed and all(
                                (person["id"], z) in self.zones for z in required
                            )
                        result = (
                            "NSS"
                            if not person
                            else "RET"
                            if item["status"] in {"ISSUED", "MISSING"}
                            else "ISS"
                            if allowed
                            else "PRM"
                        )
                    elif person or item:
                        result = "PRM"  # registered tag on wrong reader is not an intruder attempt
            n = len(self.sessions) + (
                1 if result == "IN" else -1 if result == "OUT" else 0
            )
            self.pending_results[seq] = dict(
                uid=uid,
                seq=seq,
                rd=rd,
                r=result,
                person=person.copy() if person else None,
                item=item.copy() if item else None,
                ts=self.clock(),
            )
            while len(self.pending_results) > 256:
                self.pending_results.pop(next(iter(self.pending_results)))
        self.send({"t": "AUTH", "seq": seq, "r": result, "n": n})
        if self.c.gate_photo_policy == "every_scan" and rd == 0:
            try:
                self.capture(uid, seq, result in {"IN", "OUT"})
            except Exception:
                log.exception("Optional scan photo failed")

    def confirm(self, m):
        with self.auth_lock:
            p = self.pending_results.pop(m["seq"], None)
            if not p or p["r"] != m["r"]:
                return
            result, now = p["r"], self.clock()
            uid, person, item = p["uid"], p["person"], p["item"]
            p["ts"] = now
            if result == "IN":
                self.sessions[uid] = dict(
                    id=None,
                    personnel_id=person["id"],
                    uid=uid,
                    name=person["name"],
                    expires_ts=now + self.c.session_ttl_min * 60,
                )
                p["session"] = self.sessions[uid].copy()
                self.recent = (uid, now)
            elif result == "OUT":
                p["session"] = self.sessions.pop(uid, None)
                self.recent = None
            elif item and p["rd"] == 1:
                tx = dict(
                    token=uuid.uuid4().hex,
                    ts=now,
                    kind="DENIED",
                    personnel_id=person["id"] if person else None,
                    item_id=item["id"],
                    session_id=None,
                    reader=1,
                    seq=p["seq"],
                    due_ts=None,
                    note=result,
                )
                session = next(
                    (
                        s
                        for s in self.sessions.values()
                        if person and s["personnel_id"] == person["id"]
                    ),
                    None,
                )
                if session:
                    session["expires_ts"] = now + self.c.session_ttl_min * 60
                    tx["session_id"] = session["id"]
                if result == "ISS":
                    tx.update(kind="ISSUE", due_ts=now + item["loan_minutes"] * 60)
                    self.items[uid].update(
                        status="ISSUED", holder_id=person["id"], due_ts=tx["due_ts"]
                    )
                    self.overdue.discard(item["id"])
                elif result == "RET":
                    tx["kind"] = (
                        "RETURN"
                        if item["holder_id"] == person["id"]
                        else "RETURN_OTHER"
                    )
                    self.items[uid].update(
                        status="AVAILABLE", holder_id=None, due_ts=None
                    )
                    self.overdue.discard(item["id"])
                self.enqueue("transaction", tx)
                self.reconcile.declared(tx, self.slots)
            self._current()
            if result in {"IN", "OUT"}:
                self.enqueue("session", p)
            if result not in {"DEN", "NSS", "PRM"}:
                self.fail_counter = 0

    def handle(self, m):
        if m["t"] == "FB":
            self.confirm(m)  # idempotent if reader callback already handled it
            self.drain()
            self.event("FB", m)
        elif m["t"] == "SCAN":
            self.event("SCAN", m)
        elif m["t"] == "ALARM" and m["why"] in {"SHELF_BREACH", "DEADMAN"}:
            self.alarm = True
            if (
                m["why"] == "DEADMAN"
                and not self.reconcile.pending
                and self.clock() - self.last_shelf_alarm > 2
            ):
                # Controller can finish a grace timer after the PC has restarted.
                super().handle(m)
                return
            self.drain()
            self.event("ALARM", m)
        else:
            super().handle(m)

    def slot_change(self, slot_id, old, new, details=None):
        with self.auth_lock:
            if self.monitoring_paused:
                return
            self.expire()
            slot = self.slots.get(
                slot_id, dict(id=slot_id, item_id=(details or {}).get("item_id"))
            ).copy()
            slot["issued"] = any(
                i["id"] == slot.get("item_id") and i["status"] == "ISSUED"
                for i in self.items.values()
            )
            slot["inside"] = [s["name"] for s in self.sessions.values()]
            self.reconcile.observed(slot, old, new, bool(self.sessions))
            self.enqueue(
                "event",
                {
                    "kind": "SLOT_STATE",
                    "payload": dict(
                        slot_id=slot_id, old=old, state=new, **(details or {})
                    ),
                },
            )
        if new == "ABSENT":
            try:
                self.removal_seen(slot_id)
            except Exception:
                log.exception("Prewarning evidence buffer unavailable")

    def safety_tick(self):
        # Own timer thread: no SQL, camera access or notification providers here.
        with self.auth_lock:
            self.expire()
            self.reconcile.tick()
            now = self.clock()
            if now - self.last_overdue >= self.c.overdue_check_s:
                self.last_overdue = now
                for item in self.items.values():
                    if (
                        item["status"] == "ISSUED"
                        and item["due_ts"]
                        and item["due_ts"] <= now
                        and item["id"] not in self.overdue
                    ):
                        self.overdue.add(item["id"])
                        self.enqueue("overdue", item.copy())

    def camera_health(self, camera, status, detail=""):
        if camera == "shelf":
            self.shelf_health = status
        super().camera_health(camera, status, detail)

    def drain(self):
        with self.drain_lock:
            self._drain()

    def _drain(self):
        # One event worker owns durable ordering. Leave failed job for bounded retry.
        for _ in range(256):
            try:
                if self.retry_job:
                    kind, p = self.retry_job
                else:
                    kind, p = self.jobs.get_nowait()
            except queue.Empty:
                break
            try:
                self.persist(kind, p)
            except Exception:
                self.retry_job = (kind, p)
                self.persistence_error = (
                    "Durable rules processing failed; queued work retained for retry"
                )
                log.exception(
                    "Rules persistence failed; serial/timers remain independent"
                )
                break
            else:
                self.retry_job = None
                self.persistence_error = None
                self.jobs.task_done()

    def persist(self, kind, p):
        if kind == "session":
            with self.store.session() as s:
                if p["r"] == "IN":
                    exists = s.scalar(
                        select(Session).where(
                            Session.personnel_id == p["person"]["id"],
                            Session.end_ts.is_(None),
                        )
                    )
                    if not exists:
                        exists = Session(
                            personnel_id=p["person"]["id"],
                            start_ts=p["ts"],
                            expires_ts=p["session"]["expires_ts"],
                        )
                        s.add(exists)
                        s.flush()
                    ident = exists.id
                else:
                    for v in s.scalars(
                        select(Session).where(
                            Session.personnel_id == p["person"]["id"],
                            Session.end_ts.is_(None),
                        )
                    ):
                        v.end_ts, v.end_reason = p["ts"], "BADGE_OUT"
                    ident = None
            if p["r"] == "IN":
                with self.auth_lock:
                    active = self.sessions.get(p["uid"])
                    if active and active["id"] is None:
                        active["id"] = ident
            self.event("SESSION", {"uid": p["uid"], "state": p["r"]})
        elif kind == "close":
            with self.store.session() as s:
                for v in s.scalars(
                    select(Session).where(
                        Session.personnel_id == p["personnel_id"],
                        Session.end_ts.is_(None),
                    )
                ):
                    v.end_ts, v.end_reason = self.clock(), p["reason"]
            self.event("SESSION_" + p["reason"], p)
        elif kind == "transaction":
            with self.store.session() as s:
                if not s.scalar(
                    select(Transaction.id).where(Transaction.token == p["token"])
                ):
                    if p["session_id"] is None and p["personnel_id"]:
                        active = s.scalar(
                            select(Session).where(
                                Session.personnel_id == p["personnel_id"],
                                Session.end_ts.is_(None),
                            )
                        )
                        if active:
                            p["session_id"] = active.id
                    s.add(Transaction(**p))
                    item = s.get(InventoryItem, p["item_id"])
                    if p["kind"] == "ISSUE":
                        item.status, item.holder_id, item.due_ts = (
                            "ISSUED",
                            p["personnel_id"],
                            p["due_ts"],
                        )
                    elif p["kind"] in {"RETURN", "RETURN_OTHER"}:
                        item.status, item.holder_id, item.due_ts = (
                            "AVAILABLE",
                            None,
                            None,
                        )
                    if p["session_id"]:
                        session = s.get(Session, p["session_id"])
                        if session and session.end_ts is None:
                            session.expires_ts = p["ts"] + self.c.session_ttl_min * 60
            self.publish("TRANSACTION", p)
        elif kind == "reconcile":
            ident = None
            with self.store.session() as s:
                if s.scalar(
                    select(Reconciliation.id).where(Reconciliation.token == p["token"])
                ):
                    return
                if p["alarm"] or p["warning"]:
                    incident = Incident(
                        kind=p["verdict"] + "_REMOVAL"
                        if p["verdict"] in {"NO_SESSION", "UNISSUED"}
                        else p["verdict"],
                        severity="CRITICAL" if p["alarm"] else "WARNING",
                        slot_id=p["slot_id"],
                        notes=json.dumps({"inside": p.get("inside", [])}),
                    )
                    s.add(incident)
                    s.flush()
                    ident = incident.id
                if p["alarm"] and p["item_id"]:
                    item = s.get(InventoryItem, p["item_id"])
                    if item and item.status != "ISSUED":
                        item.status = "MISSING"
                tx = (
                    s.scalar(
                        select(Transaction).where(Transaction.token == p["tx_token"])
                    )
                    if p["tx_token"]
                    else None
                )
                s.add(
                    Reconciliation(
                        token=p["token"],
                        ts=self.clock(),
                        slot_id=p["slot_id"],
                        item_id=p["item_id"],
                        observed_ts=p["observed_ts"],
                        tx_id=tx.id if tx else None,
                        verdict=p["verdict"],
                        delta_ms=p["delta_ms"],
                        incident_id=ident,
                    )
                )
            if ident:
                for callback, args in [
                    (self.evidence_for_slot, (ident, p["slot_id"])),
                    (self.alert, (ident, p["verdict"], None, "shelf", None)),
                ]:
                    try:
                        callback(*args)
                    except Exception:
                        log.exception(
                            "Optional incident I/O failed; durable verdict and alarm retained"
                        )
            self.publish("RECONCILIATION", p)
        elif kind == "overdue":
            note = json.dumps(
                {"item_id": p["id"], "due_ts": p["due_ts"], "name": p["name"]},
                sort_keys=True,
            )
            with self.store.session() as s:
                if s.scalar(
                    select(Incident.id).where(
                        Incident.kind == "OVERDUE", Incident.notes == note
                    )
                ):
                    return
            ident = self.incident("OVERDUE", notes=note)
            self.alert(ident, "OVERDUE", None, "shelf", None)
        elif kind == "event":
            self.event(p["kind"], p["payload"])
