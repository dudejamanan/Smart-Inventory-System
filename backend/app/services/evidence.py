import hashlib
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import cv2
from sqlalchemy import select
from app.db.models import CameraEvidence,Incident,FailedScan
from app.services.frames import jpeg

log=logging.getLogger(__name__)

class Evidence:
    def __init__(self,source,store,c):
        self.source,self.store,self.c=source,store,c
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='evidence')
        self.photos={}

    def record(self,incident,kind,path):
        with self.store.session() as s:
            s.add(CameraEvidence(incident_id=incident,kind=kind,path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))

    def save_photo(self,incident,kind,frame):
        directory=self.c.data_dir/'evidence'/str(incident)
        directory.mkdir(parents=True,exist_ok=True)
        path=directory/f'{kind}-{uuid.uuid4().hex}.jpg'
        path.write_bytes(jpeg(frame)); self.record(incident,kind,path)
        return path

    def schedule(self,ident):
        t0=time.monotonic()
        before=self.source.history()
        return self.pool.submit(self.capture,ident,t0,before)

    def capture(self,ident,t0,before):
        try:
            if before:
                current=min(before,key=lambda v:abs(v[0]-t0))[1]
                self.photos[ident]=self.save_photo(ident,'T0',current)
                self.save_photo(ident,'T-2',min(before,key=lambda v:abs(v[0]-(t0-2)))[1])
            time.sleep(1)
            after=self.source.history()
            if after: self.save_photo(ident,'T+1',min(after,key=lambda v:abs(v[0]-(t0+1)))[1])
            time.sleep(2)
            frames=before+[(t,f) for t,f in self.source.history() if t>t0]
            frames=sorted({t:f for t,f in frames if t0-3<=t<=t0+3}.items())
            if not frames:
                log.warning('No shelf frames available for incident %s',ident); return
            directory=self.c.data_dir/'evidence'/str(ident); directory.mkdir(parents=True,exist_ok=True)
            path=directory/'clip.mp4'; h,w=frames[0][1].shape[:2]
            writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),self.c.process_fps,(w,h))
            codec_ok=writer.isOpened()
            if codec_ok:
                # Resample to exactly six seconds, duplicating nearest available frames.
                for n in range(self.c.process_fps*6):
                    target=t0-3+n/self.c.process_fps
                    frame=min(frames,key=lambda v:abs(v[0]-target))[1]
                    writer.write(cv2.resize(frame,(w,h)))
            writer.release()
            probe=cv2.VideoCapture(str(path)) if codec_ok else None
            valid=bool(probe and probe.isOpened() and probe.read()[0])
            if probe: probe.release()
            if valid: self.record(ident,'clip',path)
            else:
                path.unlink(missing_ok=True)
                for n,(_,frame) in enumerate(frames): self.save_photo(ident,f'frame-{n:03}',frame)
        except Exception: log.exception('Evidence capture failed; alarm remains independent')

    def retention(self):
        cutoff=time.time()-self.c.retention_days*86400
        with self.store.session() as s:
            protected={i.id for i in s.scalars(select(Incident).where(Incident.keep.is_(True)))}
            kept_paths={e.path for e in s.scalars(select(CameraEvidence).where(CameraEvidence.incident_id.in_(protected)))} if protected else set()
            kept_paths.update(f.photo_path for f in s.scalars(select(FailedScan).where(FailedScan.incident_id.in_(protected))) if f.photo_path)
            for path in self.c.data_dir.rglob('*'):
                if path.suffix.lower() not in {'.jpg','.mp4'} or str(path) in kept_paths: continue
                if path.stat().st_mtime<cutoff:
                    path.unlink(missing_ok=True)
                    for e in s.scalars(select(CameraEvidence).where(CameraEvidence.path==str(path))): e.ok=False

    def close(self): self.pool.shutdown(wait=True)
