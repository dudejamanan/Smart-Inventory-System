"""Explicit SQLAlchemy schema. All timestamps are UTC Unix seconds."""
import time
from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Personnel(Base):
    __tablename__='personnel'
    id=Column(Integer, primary_key=True)
    uid=Column(String(20), unique=True, nullable=False, index=True)
    name=Column(String(120), nullable=False)
    active=Column(Boolean, default=True, nullable=False)
    created_at=Column(Float, default=time.time)

class Session(Base):
    __tablename__='sessions'
    id=Column(Integer, primary_key=True)
    personnel_id=Column(Integer, ForeignKey('personnel.id'), nullable=False)
    start_ts=Column(Float, default=time.time, index=True)
    end_ts=Column(Float, nullable=True, index=True)

Index('one_open_session', Session.end_ts, unique=True, sqlite_where=Session.end_ts.is_(None))

class InventoryItem(Base):
    __tablename__='inventory_items'
    id=Column(Integer, primary_key=True)
    name=Column(String(120), nullable=False)
    marker_id=Column(Integer, unique=True, nullable=False)
    notes=Column(Text, default='')

class Zone(Base):
    __tablename__='zones'
    id=Column(Integer, primary_key=True)
    name=Column(String(120), nullable=False)

class PersonnelZone(Base):
    __tablename__='personnel_zones'
    personnel_id=Column(Integer, ForeignKey('personnel.id'), primary_key=True)
    zone_id=Column(Integer, ForeignKey('zones.id'), primary_key=True)

class ShelfSlot(Base):
    __tablename__='shelf_slots'
    id=Column(Integer, primary_key=True)
    name=Column(String(120), nullable=False)
    roi_x=Column(Float, nullable=False)
    roi_y=Column(Float, nullable=False)
    roi_w=Column(Float, nullable=False)
    roi_h=Column(Float, nullable=False)
    marker_id=Column(Integer, nullable=False)
    item_id=Column(Integer, ForeignKey('inventory_items.id'), nullable=True)
    empty_ref_path=Column(Text, nullable=True)
    zone_id=Column(Integer, ForeignKey('zones.id'), nullable=True)

class SecurityEvent(Base):
    __tablename__='security_events'
    id=Column(Integer, primary_key=True)
    ts=Column(Float, default=time.time, index=True)
    type=Column(String(60), nullable=False, index=True)
    severity=Column(String(20), default='INFO')
    payload_json=Column(Text, default='{}')

class Incident(Base):
    __tablename__='incidents'
    id=Column(Integer, primary_key=True)
    ts=Column(Float, default=time.time, index=True)
    kind=Column(String(60), nullable=False, index=True)
    severity=Column(String(20), nullable=False)
    session_id=Column(Integer, ForeignKey('sessions.id'), nullable=True)
    slot_id=Column(Integer, ForeignKey('shelf_slots.id'), nullable=True)
    uid=Column(String(20), nullable=True)
    status=Column(String(30), default='OPEN', index=True)
    ack_ts=Column(Float, nullable=True)
    keep=Column(Boolean, default=False)
    notes=Column(Text, default='')

class FailedScan(Base):
    __tablename__='failed_scans'
    id=Column(Integer, primary_key=True)
    ts=Column(Float, default=time.time, index=True)
    uid=Column(String(20), nullable=False)
    counter=Column(Integer, nullable=False)
    photo_path=Column(Text, nullable=True)
    incident_id=Column(Integer, ForeignKey('incidents.id'), nullable=True)

class CameraEvidence(Base):
    __tablename__='camera_evidence'
    id=Column(Integer, primary_key=True)
    incident_id=Column(Integer, ForeignKey('incidents.id'), nullable=True, index=True)
    kind=Column(String(30), nullable=False)
    path=Column(Text, nullable=False, unique=True)
    sha256=Column(String(64), nullable=False)
    ts=Column(Float, default=time.time)
    ok=Column(Boolean, default=True)

class Notification(Base):
    __tablename__='notifications'
    id=Column(Integer, primary_key=True)
    incident_id=Column(Integer, ForeignKey('incidents.id'), index=True)
    channel=Column(String(20), default='whatsapp')
    to=Column(String(100), nullable=False)
    kind=Column(String(20), nullable=False)
    provider_sid=Column(String(100), nullable=True, index=True)
    status=Column(String(40), default='QUEUED')
    error_code=Column(String(40), nullable=True)
    attempts=Column(Integer, default=0)
    ts=Column(Float, default=time.time)

class CameraHealthLog(Base):
    __tablename__='camera_health_log'
    id=Column(Integer, primary_key=True)
    ts=Column(Float, default=time.time, index=True)
    camera=Column(String(20))
    status=Column(String(20))
    detail=Column(Text, default='')

class Setting(Base):
    __tablename__='settings'
    key=Column(String(100), primary_key=True)
    value=Column(Text, nullable=False)
