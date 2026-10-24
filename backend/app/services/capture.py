import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import cv2
from sqlalchemy import select
from app.db.models import FailedScan
from app.services.frames import jpeg

log=logging.getLogger(__name__)

class GateCapture:
    def __init__(self,source,store,config):
        self.source,self.store,self.c=source,store,config
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='gate-photo')
        self.futures={}
        self.lock=threading.Lock()
        self.latest=None

    def schedule(self,uid,seq,valid):
        with self.lock:
            self.futures[seq]=self.pool.submit(self.capture,uid,valid)
            if len(self.futures)>100:
                self.futures.pop(next(iter(self.futures)))

    def capture(self,uid,valid):
        if valid and not self.c.log_valid_scan_photos: return None
        frames=[]
        for _ in range(3):
            f=self.source.snapshot()
            if f is not None and time.monotonic()-self.source.last_at<3: frames.append(f)
            time.sleep(.25)
        if not frames:
            log.warning('Gate camera unavailable; security flow continues')
            return None
        frame=max(frames,key=lambda f:cv2.Laplacian(cv2.cvtColor(f,cv2.COLOR_BGR2GRAY),cv2.CV_64F).var())
        path=self.c.data_dir/'gate'/f'{uuid.uuid4().hex}.jpg'
        path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(jpeg(frame))
        self.latest=path
        if not valid:
            # FAIL is emitted immediately, capture finishes later.
            with self.store.session() as s:
                f=s.scalar(select(FailedScan).where(FailedScan.uid==uid,FailedScan.photo_path.is_(None)).order_by(FailedScan.id.desc()))
                if f: f.photo_path=str(path)
        return path

    def result(self,seq):
        with self.lock: future=self.futures.get(seq)
        try: return future.result(timeout=3) if future else None
        except Exception:
            log.exception('Gate capture failed'); return None

    def close(self): self.pool.shutdown(wait=True)
