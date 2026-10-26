"""ArUco, empty-reference classification, temporal voting and camera supervision."""

import logging
import threading
import time
import json
from collections import Counter, deque
import cv2
import numpy as np
from sqlalchemy import select
from app.db.models import ShelfSlot, InventoryItem, Setting
from app.services.frames import dictionary, jpeg

log = logging.getLogger(__name__)


def detect(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    a = cv2.aruco
    if hasattr(a, "ArucoDetector"):
        corners, ids, _ = a.ArucoDetector(
            dictionary(), a.DetectorParameters()
        ).detectMarkers(gray)
    else:
        corners, ids, _ = a.detectMarkers(
            gray, dictionary(), parameters=a.DetectorParameters_create()
        )
    h, w = gray.shape
    return (
        {}
        if ids is None
        else {
            int(i): np.mean(c[0], axis=0) / [w, h]
            for i, c in zip(ids.flatten(), corners)
        }
    )


def crop(frame, roi):
    h, w = frame.shape[:2]
    x, y, rw, rh = roi
    return frame[
        int(y * h) : max(int((y + rh) * h), int(y * h) + 1),
        int(x * w) : max(int((x + rw) * w), int(x * w) + 1),
    ]


def grayblur(frame):
    return cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (9, 9), 0)


def classify(frame, roi, marker_id, markers, empty, threshold, mode="empty_ref"):
    x, y, w, h = roi
    centre = markers.get(marker_id)
    if centre is not None and x <= centre[0] <= x + w and y <= centre[1] <= y + h:
        return "PRESENT"
    reveal = markers.get(marker_id + 20)
    if (
        mode in {"both", "reveal"}
        and reveal is not None
        and x <= reveal[0] <= x + w
        and y <= reveal[1] <= y + h
    ):
        return "ABSENT"
    if mode == "reveal":
        return "OCCLUDED"
    if empty is None:
        return "UNKNOWN" if mode == "empty_ref" else "OCCLUDED"
    current = grayblur(crop(frame, roi))
    reference = grayblur(cv2.resize(empty, (current.shape[1], current.shape[0])))
    diff = float(np.mean(cv2.absdiff(current, reference)))
    return "ABSENT" if diff < threshold else "OCCLUDED"


class Debounce:
    def __init__(self, n=4, m=5):
        self.n = n
        self.votes = deque(maxlen=m)
        self.state = "UNKNOWN"

    def vote(self, state):
        self.votes.append(state)
        if Counter(self.votes)[state] >= self.n:
            self.state = state
        return self.state


class CameraHealth:
    def __init__(self, c):
        self.c = c
        self.bad_since = None
        self.anchor_bad = None
        self.anchors = {}
        self.state = "UNKNOWN"

    def update(self, frame, last_at, now, markers):
        state = "OK"
        if frame is None or now - last_at >= self.c.cam_offline_s:
            state = "OFFLINE"
        else:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            bad = (
                float(gray.mean()) < self.c.covered_brightness
                or float(cv2.Laplacian(gray, cv2.CV_64F).var())
                < self.c.covered_variance
            )
            if bad:
                if self.bad_since is None:
                    self.bad_since = now
                if now - self.bad_since >= 2:
                    state = "COVERED"
            else:
                self.bad_since = None
            anchors = {i: p for i, p in markers.items() if 40 <= i <= 49}
            if not self.anchors and anchors:
                self.anchors = anchors
            moved = bool(self.anchors) and any(
                i not in anchors
                or np.linalg.norm(anchors[i] - pos) > self.c.anchor_tolerance
                for i, pos in self.anchors.items()
            )
            if moved:
                if self.anchor_bad is None:
                    self.anchor_bad = now
                if now - self.anchor_bad >= 3 and state == "OK":
                    state = "MOVED"
            else:
                self.anchor_bad = None
        self.state = state
        return state


class Vision:
    def __init__(self, source, store, c, engine):
        self.source, self.store, self.c, self.engine = source, store, c, engine
        self.health = CameraHealth(c)
        self.stop = threading.Event()
        self.thread = None
        self.debouncers = {}
        self.states = {}
        self.occluded_at = {}
        self.warned = set()
        self.annotated = None
        self.lock = threading.Lock()
        self.last_health = "UNKNOWN"
        self.refs = {}
        self.slots = []
        self.slot_details = {}
        self.reference_anchors = {}
        self.rectification = "Unlearned: fixed camera required"
        self.anchor_residual = None
        self.reload()

    def reload(self) -> None:
        """Cache calibrated slots so a DB outage cannot stall removal detection."""
        with self.store.session() as s:
            anchors = s.get(Setting, "vision_anchors")
            self.reference_anchors = (
                {int(k): np.array(v) for k, v in json.loads(anchors.value).items()}
                if anchors
                else {}
            )
            self.slots = list(s.scalars(select(ShelfSlot)).all())
            names = {i.id: i.name for i in s.scalars(select(InventoryItem))}
            self.slot_details = {
                slot.id: {
                    "slot_name": slot.name,
                    "item_id": slot.item_id,
                    "item_name": names.get(slot.item_id, slot.name),
                    "marker_id": slot.marker_id,
                }
                for slot in self.slots
            }
        for slot in self.slots:
            if slot.empty_ref_path:
                self.refs[slot.empty_ref_path] = cv2.imread(slot.empty_ref_path)

    def rectify(self, frame):
        h, w = frame.shape[:2]
        frame = cv2.resize(frame, (960, max(1, int(h * 960 / w))))
        if not self.reference_anchors:
            return frame
        markers = detect(frame)
        common = sorted(set(markers) & set(self.reference_anchors))
        if len(common) < 3:
            self.rectification = "MOVED: fewer than three learned anchors"
            self.anchor_residual = None
            return frame
        source = np.float32([markers[i] for i in common])
        dest = np.float32([self.reference_anchors[i] for i in common])
        # Three correspondences determine an affine map; projective needs four.
        if len(common) == 3:
            matrix = np.vstack([cv2.getAffineTransform(source, dest), [0, 0, 1]])
        else:
            matrix, _ = cv2.findHomography(source, dest, cv2.RANSAC, 0.01)
        if matrix is None or not np.isfinite(matrix).all():
            self.rectification = "MOVED: invalid anchor geometry"
            return frame
        transformed = cv2.perspectiveTransform(source.reshape(1, -1, 2), matrix)[0]
        self.anchor_residual = float(np.max(np.linalg.norm(transformed - dest, axis=1)))
        # Reject singular/implausible fits, including scale collapse and flipped planes.
        if (
            self.anchor_residual > 0.02
            or np.linalg.det(matrix[:2, :2]) <= 0.1
            or np.linalg.cond(matrix) > 100
        ):
            self.rectification = "MOVED: anchor fit rejected"
            return frame
        size = np.diag([frame.shape[1], frame.shape[0], 1])
        self.rectification = (
            "RECTIFIED" if len(common) >= 4 else "AFFINE (three anchors)"
        )
        return cv2.warpPerspective(
            frame, size @ matrix @ np.linalg.inv(size), (frame.shape[1], frame.shape[0])
        )

    def learn(self):
        frame = self.source.snapshot()
        if (
            frame is None
            or time.monotonic() - self.source.last_at >= self.c.cam_offline_s
        ):
            raise ValueError("Shelf camera must be live before learning")
        markers = detect(frame)
        anchors = {i: p.tolist() for i, p in markers.items() if 40 <= i <= 49}
        if len(anchors) < 4:
            raise ValueError(
                "Show at least four anchors (40–49) around the shelf; all items must be present"
            )
        points = np.float32(list(anchors.values()))
        if cv2.contourArea(cv2.convexHull(points)) < 0.03:
            raise ValueError(
                "Spread anchors around the shelf rather than along one line"
            )
        missing = [s.marker_id for s in self.slots if s.marker_id not in markers]
        if missing:
            raise ValueError(
                f"All configured item markers must be visible: missing {missing}"
            )
        with self.store.session() as s:
            s.merge(Setting(key="vision_anchors", value=json.dumps(anchors)))
            for slot in s.scalars(select(ShelfSlot)):
                x, y = markers[slot.marker_id]
                # Starter ROI around resting marker; operator refines box extent in UI.
                slot.roi_x = max(0, float(x) - 0.10)
                slot.roi_y = max(0, float(y) - 0.15)
                slot.roi_w = min(0.20, 1 - slot.roi_x)
                slot.roi_h = min(0.30, 1 - slot.roi_y)
                slot.empty_ref_path = None
        self.health.anchors = {i: np.array(p) for i, p in anchors.items()}
        self.debouncers.clear()
        self.reload()
        return {
            "ok": True,
            "anchors": len(anchors),
            "slots": len(self.slots),
            "message": "Rest positions learned. Refine ROIs, then verify each reveal marker and capture empty references.",
        }

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def process(self):
        frame = self.source.snapshot()
        now = time.monotonic()
        if frame is not None:
            frame = self.rectify(frame)
        markers = detect(frame) if frame is not None else {}
        status = self.health.update(frame, self.source.last_at, now, markers)
        if (
            self.reference_anchors
            and self.rectification.startswith("MOVED")
            and status == "OK"
        ):
            status = self.health.state = "MOVED"
        if status != self.last_health:
            self.last_health = status
            self.engine.camera_health("shelf", status)
        if frame is None:
            return
        slots = self.slots
        for slot in slots:
            roi = (slot.roi_x, slot.roi_y, slot.roi_w, slot.roi_h)
            path = slot.empty_ref_path
            if path and path not in self.refs:
                self.refs[path] = cv2.imread(path)
            empty = self.refs.get(path) if path else None
            vote = (
                classify(
                    frame,
                    roi,
                    slot.marker_id,
                    markers,
                    empty,
                    self.c.empty_diff_thresh,
                    self.c.slot_mode,
                )
                if status == "OK"
                else "UNKNOWN"
            )
            deb = self.debouncers.setdefault(
                slot.id, Debounce(self.c.debounce_n, self.c.debounce_m)
            )
            old = deb.state
            new = deb.vote(vote)
            self.states[slot.id] = new
            if old != new:
                self.engine.slot_change(
                    slot.id, old, new, self.slot_details.get(slot.id)
                )
                if new == "OCCLUDED":
                    self.occluded_at[slot.id] = now
                else:
                    self.occluded_at.pop(slot.id, None)
                    self.warned.discard(slot.id)
            if (
                new == "OCCLUDED"
                and now - self.occluded_at.get(slot.id, now) >= self.c.occluded_warn_s
                and slot.id not in self.warned
            ):
                self.warned.add(slot.id)
                self.engine.occluded(slot.id)
            x, y, w, h = roi
            fh, fw = frame.shape[:2]
            color = {
                "PRESENT": (90, 150, 35),
                "ABSENT": (50, 50, 215),
                "OCCLUDED": (30, 165, 215),
            }.get(new, (140, 140, 140))
            cv2.rectangle(
                frame,
                (int(x * fw), int(y * fh)),
                (int((x + w) * fw), int((y + h) * fh)),
                color,
                2,
            )
            cv2.putText(
                frame,
                f"{slot.name} / #{slot.marker_id} / {new}",
                (int(x * fw), max(20, int(y * fh) - 8)),
                0,
                0.46,
                color,
                1,
            )
        with self.lock:
            self.annotated = jpeg(frame)

    def run(self):
        while not self.stop.is_set():
            started = time.monotonic()
            try:
                self.process()
            except Exception:
                log.exception("Vision processing error")
            self.stop.wait(
                max(0.01, 1 / self.c.process_fps - (time.monotonic() - started))
            )

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(3)
