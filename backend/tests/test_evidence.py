import hashlib
import os
import time
from unittest.mock import Mock
from sqlalchemy import select
from app.config import Config
from app.db.store import Store
from app.db.models import Incident, CameraEvidence, ShelfSlot
from app.services.evidence import Evidence
from app.services.frames import SyntheticShelfSource


def test_codec_fallback_and_hashes(tmp_path, monkeypatch):
    c = Config(data_dir=tmp_path)
    store = Store(c)
    source = SyntheticShelfSource()
    with store.session() as s:
        incident = Incident(kind="SHELF_BREACH", severity="CRITICAL")
        s.add(incident)
        s.flush()
        ident = incident.id
    frame = source.grab()
    now = time.monotonic()
    source.ring.extend([(now - 2, frame), (now, frame), (now + 1, frame)])
    monkeypatch.setattr("app.services.evidence.time.sleep", lambda _: None)
    writer = Mock()
    writer.isOpened.return_value = False
    monkeypatch.setattr("app.services.evidence.cv2.VideoWriter", lambda *args: writer)
    evidence = Evidence(source, store, c)
    evidence.capture(ident, now, source.history())
    with store.session() as s:
        rows = s.scalars(select(CameraEvidence)).all()
        assert any(r.kind.startswith("frame-") for r in rows)
        from pathlib import Path

        assert all(
            r.sha256 == hashlib.sha256(Path(r.path).read_bytes()).hexdigest()
            for r in rows
        )
    evidence.close()
    store.engine.dispose()


def test_retention_preserves_keep_and_calibration(tmp_path):
    c = Config(data_dir=tmp_path, retention_days=1)
    store = Store(c)
    store.seed()
    kept = tmp_path / "keep.jpg"
    old = tmp_path / "old.jpg"
    reference = tmp_path / "reference.jpg"
    for path in [kept, old, reference]:
        path.write_bytes(b"image")
        os.utime(path, (1, 1))
    with store.session() as s:
        incident = Incident(kind="TEST", severity="WARNING", keep=True)
        s.add(incident)
        s.flush()
        s.add(
            CameraEvidence(
                incident_id=incident.id, kind="T0", path=str(kept), sha256="test"
            )
        )
        slot = s.get(ShelfSlot, 1)
        slot.empty_ref_path = str(reference)
    evidence = Evidence(SyntheticShelfSource(), store, c)
    evidence.retention()
    assert kept.exists() and reference.exists() and not old.exists()
    evidence.close()
    store.engine.dispose()
