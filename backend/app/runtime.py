import asyncio
import logging
import queue
import secrets
import threading
import time
from sqlalchemy import select
from app.db.store import Store
from app.db.models import ShelfSlot,Setting
from app.services.engine import Engine
from app.services.serial_link import SerialLink
from app.services.frames import WebcamSource,MjpegUrlSource,VideoFileSource,SyntheticShelfSource,jpeg
from app.services.vision import Vision,crop
from app.services.capture import GateCapture
from app.services.evidence import Evidence
from app.services.notifier import MediaSigner,NotificationQueue

log=logging.getLogger(__name__)
SAFE_SETTINGS={'fail_limit','fail_window_s','alarm_s','empty_diff_thresh','retention_days',
               'log_valid_scan_photos','whatsapp_on','zones_enabled','debounce_n','debounce_m','occluded_warn_s'}

class Runtime:
    def __init__(self,c,simulate=False):
        self.c,self.simulate=c,simulate
        self.store=Store(c)
        with self.store.session() as s:
            overrides={v.key:__import__('json').loads(v.value) for v in s.scalars(select(Setting)) if v.key in SAFE_SETTINGS}
        if overrides:
            validated=type(c)(**(c.model_dump()|overrides))
            for key in overrides: setattr(c,key,getattr(validated,key))
        if simulate: self.store.seed()
        self.events=queue.Queue(maxsize=2048)
        self.stop=threading.Event(); self.started=time.monotonic()
        self.clients=set(); self.loop=None
        self.engine=Engine(self.store,c,lambda m:self.serial.send(m))
        self.serial=SerialLink(c,self.on_serial,simulate)
        self.serial.on_connect=self.engine.sync
        self.gate=SyntheticShelfSource(gate=True) if simulate else WebcamSource(c.gate_camera_index)
        self.shelf=(SyntheticShelfSource(c.process_fps) if simulate else
                    VideoFileSource(c.shelf_video_file,fps=c.process_fps) if c.shelf_video_file else
                    MjpegUrlSource(c.shelf_stream_url,c.process_fps))
        self.capture=GateCapture(self.gate,self.store,c)
        self.evidence=Evidence(self.shelf,self.store,c)
        self.signer=MediaSigner(c.data_dir,c.media_url_secret or secrets.token_hex(32))
        self.notifications=NotificationQueue(self.store,c,self.signer)
        self.vision=Vision(self.shelf,self.store,c,self.engine)
        self.engine.capture=self.capture.schedule
        self.engine.alert=self.notifications.enqueue
        self.engine.evidence=self.evidence.schedule
        self.engine.publish=self.publish
        self.notifications.photo=self.notification_photo
        self.worker=None

    def notification_photo(self,source,seq):
        if source=='gate':
            path=self.capture.result(seq)
            if path:
                # Associate photos with gate incidents for dashboard and retention.
                from app.db.models import FailedScan,CameraEvidence
                with self.store.session() as s:
                    failed=s.scalar(select(FailedScan).where(FailedScan.photo_path==str(path)))
                    incident=failed.incident_id if failed else None
                    exists=s.scalar(select(CameraEvidence.id).where(CameraEvidence.path==str(path)))
                if incident and not exists: self.evidence.record(incident,'gate',path)
            return path
        frame=self.shelf.snapshot()
        if frame is None: return None
        path=self.c.data_dir/'outgoing'/f'shelf-{secrets.token_hex(8)}.jpg'
        path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(jpeg(frame))
        return path

    def on_serial(self,m):
        self.engine.authorize(m)
        try: self.events.put_nowait(m)
        except queue.Full: log.error('Event queue full; local UNO alarm remains operational')

    def publish(self,kind,payload):
        if self.loop and self.clients:
            for client in list(self.clients):
                def put(q=client):
                    if q.full():
                        try: q.get_nowait()
                        except asyncio.QueueEmpty: pass
                    q.put_nowait({'type':kind,'payload':payload})
                self.loop.call_soon_threadsafe(put)

    def run_events(self):
        last_retention=0.; last_gate='UNKNOWN'; last_serial=True
        while not self.stop.is_set() or not self.events.empty():
            try:
                m=self.events.get(timeout=.1)
                try: self.engine.handle(m)
                finally: self.events.task_done()
            except queue.Empty: pass
            except Exception: log.exception('Event processing failed')
            now=time.monotonic()
            try:
                gate='OK' if self.gate.last_at and now-self.gate.last_at<self.c.cam_offline_s else 'OFFLINE'
                if gate!=last_gate:
                    last_gate=gate; self.engine.camera_health('gate',gate,self.gate.error)
                connected=self.serial.connected and now-self.serial.last_rx<self.c.pc_lost_s
                if connected!=last_serial and now-self.started>self.c.pc_lost_s:
                    last_serial=connected; self.engine.event('SERIAL_HEALTH',{'connected':connected})
                if now-last_retention>3600:
                    last_retention=now; self.evidence.retention()
            except Exception: log.exception('Health or retention job failed')

    def start(self):
        self.gate.start(); self.shelf.start()
        if self.simulate:
            with self.store.session() as s:
                for slot in s.scalars(select(ShelfSlot)):
                    if not slot.empty_ref_path:
                        path=self.c.data_dir/f'empty-{slot.id}.jpg'
                        path.write_bytes(jpeg(crop(self.shelf.empty(),(slot.roi_x,slot.roi_y,slot.roi_w,slot.roi_h))))
                        slot.empty_ref_path=str(path)
        self.notifications.start()
        self.worker=threading.Thread(target=self.run_events,daemon=True); self.worker.start()
        self.serial.start(); self.vision.start()

    def status(self):
        now=time.monotonic()
        return {'simulate':self.simulate,'uptime_s':int(now-self.started),
                'serial':{'connected':self.serial.connected and now-self.serial.last_rx<self.c.pc_lost_s,
                          'malformed':self.serial.malformed},
                'session':self.engine.current,'alarm':self.engine.alarm,'fail_counter':self.engine.fail_counter,
                'gate_camera':'OK' if self.gate.last_at and now-self.gate.last_at<3 else 'OFFLINE',
                'shelf_camera':self.vision.health.state,'slots':self.vision.states,
                'whatsapp_remaining_s':self.notifications.session_remaining(),
                'notifier':type(self.notifications.provider).__name__,
                'enrolled_uid':self.engine.enrolled_uid}

    def close(self):
        self.vision.close(); self.serial.close()
        self.stop.set()
        if self.worker: self.worker.join(4)
        self.capture.close(); self.evidence.close(); self.notifications.close()
        self.gate.close(); self.shelf.close(); self.store.engine.dispose()
