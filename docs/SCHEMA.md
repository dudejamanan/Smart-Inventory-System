# SQLite schema

SQLAlchemy model source: `backend/app/db/models.py`. SQLite WAL, foreign_keys ON, busy_timeout 10000 ms. Integer primary keys except composite permission keys and settings.key. Times are float UTC Unix seconds. Schema is created on first run; this version has no migration engine. Back up `data/warehouse.db` before changing models or dependency versions. Stop the app for a consistent file backup, including WAL/SHM files if still present.

| Table | Columns / relationships |
|---|---|
| personnel | id, uid UNIQUE indexed, name, active, created_at |
| sessions | id, personnel_id -> personnel, start_ts indexed, end_ts nullable indexed |
| inventory_items | id, name, marker_id UNIQUE (0–29), notes |
| shelf_slots | id, name, roi_x/y/w/h normalized, marker_id, item_id -> inventory_items, empty_ref_path, zone_id -> zones nullable |
| security_events | id, ts indexed, type indexed, severity, payload_json |
| incidents | id, ts indexed, kind indexed, severity, session_id -> sessions nullable, slot_id -> shelf_slots nullable, uid nullable, status indexed, ack_ts nullable, keep, notes |
| failed_scans | id, ts indexed, uid, counter, photo_path nullable, incident_id -> incidents nullable |
| camera_evidence | id, incident_id -> incidents indexed nullable, kind, path, sha256, ts, ok |
| notifications | id, incident_id -> incidents indexed, channel, to, kind (text/media), provider_sid indexed nullable, status, error_code nullable, attempts, ts |
| camera_health_log | id, ts indexed, camera, status, detail |
| settings | key PRIMARY KEY, value (JSON for safe settings; owner inbound time is numeric text) |
| zones | id, name |
| personnel_zones | personnel_id -> personnel + zone_id -> zones, composite PRIMARY KEY |

Open sessions have end_ts NULL and the engine opens/closes them serially. History restricts deletion of referenced personnel/items; deactivate personnel instead. Incident states: OPEN and ACKNOWLEDGED. Notification states include QUEUED, SENDING, RETRYING, provider states, MOCK_SENT, RATE_LIMITED, NO_PHOTO, FAILED, FAILED_MEDIA and FAILED_SESSION_EXPIRED. Failed capture is represented by no evidence row and a camera-health event; expired evidence retains its row with ok=false.

Seed demo data: from `backend/`, `python -m app --seed`. This explicitly authorizes the documented fake cards and should not be used for a real access-control whitelist. Simulation seeds automatically. The default DB has no real credentials or personal data.
