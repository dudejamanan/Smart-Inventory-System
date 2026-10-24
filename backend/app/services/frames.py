"""Latest-frame grabbers with timestamped five-second rings and reconnect backoff."""

import logging
import threading
import time
from collections import deque
import cv2
import numpy as np

log = logging.getLogger(__name__)


def dictionary():
    a = cv2.aruco
    return (
        a.getPredefinedDictionary(a.DICT_4X4_50)
        if hasattr(a, "getPredefinedDictionary")
        else a.Dictionary_get(a.DICT_4X4_50)
    )


def marker(ident: int, size: int = 180):
    a = cv2.aruco
    if hasattr(a, "generateImageMarker"):
        return a.generateImageMarker(dictionary(), ident, size)
    return a.drawMarker(dictionary(), ident, size)


class FrameSource:
    def __init__(self, fps=10):
        self.fps = fps
        self.lock = threading.RLock()
        self.ring = deque(maxlen=max(60, int(fps * 6)))
        self.latest = None
        self.last_at = 0.0
        self.stop = threading.Event()
        self.thread = None
        self.error = ""

    def grab(self):
        raise NotImplementedError

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        backoff = 0.2
        while not self.stop.is_set():
            started = time.monotonic()
            try:
                frame = self.grab()
                if frame is None:
                    raise OSError("No camera frame")
                with self.lock:
                    self.last_at = time.monotonic()
                    self.latest = frame
                    self.ring.append((self.last_at, frame.copy()))
                    while self.ring and self.last_at - self.ring[0][0] > 5:
                        self.ring.popleft()
                self.error = ""
                backoff = 0.2
            except Exception as exc:
                self.error = str(exc)
                log.warning("Camera: %s", exc)
                self.release()
                self.stop.wait(backoff)
                backoff = min(backoff * 2, 5)
            self.stop.wait(max(0, 1 / self.fps - (time.monotonic() - started)))
        self.release()

    def snapshot(self):
        with self.lock:
            return None if self.latest is None else self.latest.copy()

    def history(self):
        with self.lock:
            return [(t, f.copy()) for t, f in self.ring]

    def release(self):
        pass

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(4)


class CaptureSource(FrameSource):
    def __init__(self, source, fps=10, loop=False):
        super().__init__(fps)
        self.source, self.loop, self.cap = source, loop, None

    def grab(self):
        if self.cap is None:
            self.cap = cv2.VideoCapture()
            # FFmpeg timeouts bound network stalls where supported.
            if isinstance(self.source, str) and "://" in self.source:
                self.cap.open(
                    self.source,
                    cv2.CAP_FFMPEG,
                    [
                        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
                        2000,
                        cv2.CAP_PROP_READ_TIMEOUT_MSEC,
                        2000,
                    ],
                )
            else:
                self.cap.open(self.source)
        ok, frame = self.cap.read()
        if not ok and self.loop:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
        return frame if ok else None

    def release(self):
        if self.cap:
            self.cap.release()
        self.cap = None


class WebcamSource(CaptureSource):
    def __init__(self, index=0, fps=10):
        super().__init__(index, fps)


class MjpegUrlSource(CaptureSource):
    pass


class VideoFileSource(CaptureSource):
    def __init__(self, path, loop=True, fps=10):
        super().__init__(path, fps, loop)


class SyntheticShelfSource(FrameSource):
    def __init__(self, fps=10, gate=False):
        super().__init__(fps)
        self.states = {0: "present", 1: "present", 2: "present"}
        self.covered = False
        self.offline = False
        self.moved = False
        self.gate = gate

    def empty(self):
        image = np.full((540, 960, 3), 220, np.uint8)
        for y in [115, 445]:
            cv2.line(image, (25, y), (935, y), (80, 92, 100), 8)
        for x in [30, 330, 630, 930]:
            cv2.line(image, (x, 115), (x, 445), (120, 125, 130), 4)
        return image

    def grab(self):
        if self.offline:
            return None
        if self.covered:
            return np.zeros((540, 960, 3), np.uint8)
        image = self.empty()
        if self.gate:
            cv2.circle(image, (480, 200), 75, (160, 125, 95), -1)
            cv2.ellipse(image, (480, 430), (125, 145), 0, 180, 360, (140, 95, 60), -1)
            cv2.putText(
                image, "SIMULATED GATE CAMERA", (235, 500), 0, 0.8, (40, 40, 40), 2
            )
            return image
        for ident, state in self.states.items():
            x = 75 + ident * 298
            if state == "present":
                cv2.rectangle(image, (x, 170), (x + 200, 400), (165, 186, 200), -1)
                image[215:355, x + 30 : x + 170] = cv2.cvtColor(
                    marker(ident, 140), cv2.COLOR_GRAY2BGR
                )
            elif state == "occluded":
                cv2.rectangle(image, (x, 170), (x + 200, 400), (70, 110, 170), -1)
        for ident, x in [(40, 70), (41, 800)]:
            offset = 40 if self.moved else 0
            image[20:80, x + offset : x + offset + 60] = cv2.cvtColor(
                marker(ident, 60), cv2.COLOR_GRAY2BGR
            )
        return image


def jpeg(frame, quality=85):
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise OSError("JPEG encoding failed")
    return buf.tobytes()
