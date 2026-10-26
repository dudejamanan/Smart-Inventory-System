"""Explicit SQLAlchemy schema. All timestamps are UTC Unix seconds."""

import time
from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Personnel(Base):
    __tablename__ = "personnel"
    id = Column(Integer, primary_key=True)
    uid = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(120), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    level = Column(Integer, default=1, nullable=False)
    created_at = Column(Float, default=time.time)


class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    personnel_id = Column(Integer, ForeignKey("personnel.id"), nullable=False)
    start_ts = Column(Float, default=time.time, index=True)
    end_ts = Column(Float, nullable=True, index=True)
    expires_ts = Column(Float, nullable=True)
    end_reason = Column(String(20), nullable=True)


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    marker_id = Column(Integer, unique=True, nullable=False)
    notes = Column(Text, default="")
    tag_uid = Column(String(20), unique=True, nullable=True)
    min_level = Column(Integer, default=1, nullable=False)
    loan_minutes = Column(Integer, default=60, nullable=False)
    status = Column(String(20), default="AVAILABLE", nullable=False)
    holder_id = Column(Integer, ForeignKey("personnel.id"), nullable=True)
    due_ts = Column(Float, nullable=True)


class Zone(Base):
    __tablename__ = "zones"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)


class PersonnelZone(Base):
    __tablename__ = "personnel_zones"
    personnel_id = Column(Integer, ForeignKey("personnel.id"), primary_key=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), primary_key=True)


class ShelfSlot(Base):
    __tablename__ = "shelf_slots"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    roi_x = Column(Float, nullable=False)
    roi_y = Column(Float, nullable=False)
    roi_w = Column(Float, nullable=False)
    roi_h = Column(Float, nullable=False)
    marker_id = Column(Integer, nullable=False)
    item_id = Column(Integer, ForeignKey("inventory_items.id"), nullable=True)
    empty_ref_path = Column(Text, nullable=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=True)


class SecurityEvent(Base):
    __tablename__ = "security_events"
    id = Column(Integer, primary_key=True)
    ts = Column(Float, default=time.time, index=True)
    type = Column(String(60), nullable=False, index=True)
    severity = Column(String(20), default="INFO")
    payload_json = Column(Text, default="{}")


class Incident(Base):
    __tablename__ = "incidents"
    id = Column(Integer, primary_key=True)
    ts = Column(Float, default=time.time, index=True)
    kind = Column(String(60), nullable=False, index=True)
    severity = Column(String(20), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    slot_id = Column(Integer, ForeignKey("shelf_slots.id"), nullable=True)
    uid = Column(String(20), nullable=True)
    status = Column(String(30), default="OPEN", index=True)
    ack_ts = Column(Float, nullable=True)
    keep = Column(Boolean, default=False)
    notes = Column(Text, default="")


class FailedScan(Base):
    __tablename__ = "failed_scans"
    id = Column(Integer, primary_key=True)
    ts = Column(Float, default=time.time, index=True)
    uid = Column(String(20), nullable=False)
    counter = Column(Integer, nullable=False)
    photo_path = Column(Text, nullable=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=True)


class CameraEvidence(Base):
    __tablename__ = "camera_evidence"
    id = Column(Integer, primary_key=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=True, index=True)
    kind = Column(String(30), nullable=False)
    path = Column(Text, nullable=False)
    sha256 = Column(String(64), nullable=False)
    ts = Column(Float, default=time.time)
    ok = Column(Boolean, default=True)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), index=True)
    channel = Column(String(20), default="whatsapp")
    to = Column(String(100), nullable=False)
    kind = Column(String(20), nullable=False)
    provider_sid = Column(String(100), nullable=True, index=True)
    status = Column(String(40), default="QUEUED")
    error_code = Column(String(40), nullable=True)
    attempts = Column(Integer, default=0)
    ts = Column(Float, default=time.time)


class CameraHealthLog(Base):
    __tablename__ = "camera_health_log"
    id = Column(Integer, primary_key=True)
    ts = Column(Float, default=time.time, index=True)
    camera = Column(String(20))
    status = Column(String(20))
    detail = Column(Text, default="")


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)


class OfflineRecord(Base):
    __tablename__ = "offline_records"
    board_id = Column(String(80), primary_key=True)
    boot_id = Column(Integer, primary_key=True)
    event_id = Column(Integer, primary_key=True)
    uid_hash = Column(String(8), nullable=False)
    event = Column(String(4), nullable=False)
    observed_ts = Column(Float, nullable=False)
    received_ts = Column(Float, nullable=False)


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    token = Column(String(40), unique=True, nullable=False)
    ts = Column(Float, nullable=False, index=True)
    kind = Column(String(20), nullable=False)
    personnel_id = Column(Integer, ForeignKey("personnel.id"), nullable=True)
    item_id = Column(Integer, ForeignKey("inventory_items.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    reader = Column(Integer, nullable=False)
    seq = Column(Integer, nullable=False)
    due_ts = Column(Float, nullable=True)
    note = Column(Text, default="")


class Reconciliation(Base):
    __tablename__ = "reconciliations"
    id = Column(Integer, primary_key=True)
    token = Column(String(40), unique=True, nullable=True)
    ts = Column(Float, nullable=False)
    slot_id = Column(Integer, ForeignKey("shelf_slots.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("inventory_items.id"), nullable=True)
    observed_ts = Column(Float, nullable=False)
    tx_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    verdict = Column(String(30), nullable=False)
    delta_ms = Column(Integer, nullable=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=True)
