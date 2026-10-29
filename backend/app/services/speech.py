"""Bounded local speech queue. Only its worker owns pyttsx3/SAPI and COM.

Serial/timer callers enqueue fixed phrases only; they never wait for speech.
"""

from collections import deque
from dataclasses import dataclass
import logging
import sys
import threading
import time

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Utterance:
    text: str
    category: str
    priority: int
    expires: float
    revision: int = 0


class SpeechQueue:
    def __init__(
        self,
        config,
        *,
        simulate=False,
        engine_factory=None,
        clock=time.monotonic,
        capacity=16,
    ):
        self.c, self.simulate, self.clock = config, simulate, clock
        self.factory = engine_factory
        self.capacity = capacity
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.stop = threading.Event()
        self.thread = None
        self.pending = deque()
        self.active = None
        self.active_at = 0.0
        self.interrupt = False
        self.last_key = {}
        self.revisions = {}
        self.dropped = self.completed = self.interrupted = 0
        self.error = None
        self.last_phrase = None
        self.voices = []
        self.ready = False
        self.engine = None
        self.properties = None
        self.driver_error = None
        self.retry_at = 0.0
        self.com = None

    @property
    def enabled(self):
        return self.c.tts_enabled and (not self.simulate or self.c.tts_in_simulation)

    def say(self, key, text, *, priority=20, category="routine", ttl=6, cooldown=2):
        if not self.enabled or self.stop.is_set():
            return False
        now = self.clock()
        with self.lock:
            if now - self.last_key.get(key, -1e20) < cooldown:
                return False
            self.last_key[key] = now
            if len(self.last_key) > 256:
                self.last_key.pop(next(iter(self.last_key)))
            if priority == 0:
                # Old successes must not be spoken after a newer security alarm.
                kept = deque(m for m in self.pending if m.priority == 0)
                self.dropped += len(self.pending) - len(kept)
                self.pending = kept
            if len(self.pending) >= self.capacity:
                worst = max(
                    range(len(self.pending)), key=lambda i: self.pending[i].priority
                )
                if self.pending[worst].priority <= priority:
                    self.dropped += 1
                    return False
                del self.pending[worst]
                self.dropped += 1
            self.pending.append(
                Utterance(
                    text, category, priority, now + ttl, self.revisions.get(category, 0)
                )
            )
            if self.active and priority < self.active.priority:
                self.interrupt = True
        self.wake.set()
        return True

    def cancel(self, category):
        with self.lock:
            self.revisions[category] = self.revisions.get(category, 0) + 1
            self.pending = deque(m for m in self.pending if m.category != category)
            if self.active and self.active.category == category:
                self.interrupt = True
        self.wake.set()

    def refresh_settings(self):
        if not self.enabled:
            with self.lock:
                self.pending.clear()
                self.interrupt = True
        self.wake.set()

    def test(self):
        # A speech test never dispatches an Arduino alarm or sends notifications.
        self.retry_at = 0
        return self.say(
            "test",
            "Voice test. Access granted. Access denied. Security alarm.",
            priority=5,
            category="test",
            ttl=15,
            cooldown=3,
        )

    def _init_engine(self):
        if self.engine is not None:
            return
        if self.factory is None:
            if sys.platform == "win32" and self.com is None:
                import pythoncom

                pythoncom.CoInitialize()
                self.com = pythoncom
            import pyttsx3

            self.engine = pyttsx3.init(
                driverName="sapi5" if sys.platform == "win32" else None
            )
        else:
            self.engine = self.factory()
        self.engine.connect("error", self._engine_error)
        # An externally pumped loop allows stop/mute/urgent preemption from the
        # SAME owner thread. runAndWait() would block those controls.
        self.engine.startLoop(False)
        self.engine.iterate()
        voices = self.engine.getProperty("voices") or []
        with self.lock:
            self.voices = [{"id": v.id, "name": v.name} for v in voices]
        self.ready = True
        self.error = None

    def _engine_error(self, name, exception):
        self.driver_error = type(exception).__name__

    def _dispose(self):
        if self.engine is not None:
            try:
                self.engine.stop()
                self.engine.endLoop()
            except Exception:
                pass
        self.engine = None
        self.ready = False
        self.properties = None
        self.driver_error = None

    def _step(self):
        # Called only by the worker (or tests using a fake engine).
        with self.lock:
            interrupt = self.interrupt or not self.enabled
            self.interrupt = False
        if interrupt and self.engine is not None and self.active:
            self.engine.stop()
            self.interrupted += 1
            with self.lock:
                self.active = None
        if self.engine is not None:
            self.engine.iterate()
            if self.driver_error:
                raise RuntimeError("Speech driver reported an error")
            if self.active and not self.engine.isBusy():
                self.completed += 1
                with self.lock:
                    self.active = None
            elif self.active and self.clock() - self.active_at > 20:
                raise TimeoutError("Speech utterance timed out")
        if self.active or not self.enabled or self.clock() < self.retry_at:
            return
        with self.lock:
            kept = deque(m for m in self.pending if m.expires > self.clock())
            self.dropped += len(self.pending) - len(kept)
            self.pending = kept
            if not self.pending:
                return
            index = min(
                range(len(self.pending)), key=lambda i: self.pending[i].priority
            )
            message = self.pending[index]
            del self.pending[index]
        self._init_engine()
        properties = (self.c.tts_rate, self.c.tts_volume, self.c.tts_voice)
        if properties != self.properties:
            self.engine.setProperty("rate", properties[0])
            self.engine.setProperty("volume", properties[1])
            if properties[2]:
                voice = next(
                    (v for v in self.voices if properties[2] in {v["id"], v["name"]}),
                    None,
                )
                if voice is None:
                    raise ValueError("Configured voice is unavailable")
                self.engine.setProperty("voice", voice["id"])
            elif self.properties and self.properties[2]:
                # Restore the engine's platform default after clearing a voice.
                self._dispose()
                self._init_engine()
                self.engine.setProperty("rate", properties[0])
                self.engine.setProperty("volume", properties[1])
            self.properties = properties
        with self.lock:
            # Mute may have arrived while the speech engine was initializing.
            if not self.enabled or message.revision != self.revisions.get(
                message.category, 0
            ):
                return
            if any(m.priority < message.priority for m in self.pending):
                self.dropped += 1
                return
            self.active = message
            self.last_phrase = message.text
            self.active_at = self.clock()
        self.engine.say(message.text)
        self.engine.iterate()

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(
                target=self.run, daemon=True, name="local-speech"
            )
            self.thread.start()

    def run(self):
        try:
            while not self.stop.is_set():
                try:
                    self._step()
                except Exception as exc:
                    self.error = f"Local speech unavailable ({type(exc).__name__}). Check the installed voice/audio driver or test voice again."
                    log.warning(
                        "Local speech failed: %s; security processing continues",
                        type(exc).__name__,
                    )
                    self._dispose()
                    with self.lock:
                        self.dropped += len(self.pending)
                        self.pending.clear()
                        self.active = None
                    self.retry_at = self.clock() + 30
                self.wake.wait(0.02 if self.active else 0.1)
                self.wake.clear()
        finally:
            self._dispose()
            if self.com is not None:
                self.com.CoUninitialize()
                self.com = None

    def status(self):
        with self.lock:
            return {
                "enabled": self.enabled,
                "ready": self.ready,
                "speaking": self.active is not None,
                "queued": len(self.pending),
                "completed": self.completed,
                "dropped": self.dropped,
                "interrupted": self.interrupted,
                "error": self.error,
                "last_phrase": self.last_phrase,
                "voices": list(self.voices),
                "rate": self.c.tts_rate,
                "volume": self.c.tts_volume,
                "simulation_muted": self.simulate and not self.c.tts_in_simulation,
            }

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.thread:
            self.thread.join(2)


class Announcer:
    """Fixed event phrases, no names/UIDs or arbitrary remote text spoken aloud."""

    def __init__(self, speech):
        self.speech = speech
        self.seen_feedback = deque(maxlen=256)
        self.enrol_sequences = set()
        self.alarm = False
        self.prewarn = False
        self.boot = None
        self.cameras = {}
        self.lock = threading.RLock()

    def _alarm(self, reason):
        self.prewarn = False
        self.speech.cancel("prewarn")
        if not self.alarm:
            self.alarm = True
            text = (
                "Security alarm. Three failed access attempts."
                if reason == "GATE_3_FAIL"
                else "Security alarm. Unauthorised shelf removal."
                if reason in {"SHELF_BREACH", "DEADMAN"}
                else "Security alarm. Please check the dashboard."
            )
            self.speech.say(
                "alarm", text, priority=0, category="alarm", ttl=20, cooldown=0
            )

    def command(self, m):
        with self.lock:
            self._command(m)

    def _command(self, m):
        if m["t"] == "ALARM" and m.get("on") == 1:
            self._alarm(m.get("why"))
        elif m["t"] == "PW":
            if m["on"]:
                if not self.prewarn and not self.alarm:
                    self.speech.say(
                        "prewarn",
                        "Warning. Scan the item before the grace period expires.",
                        priority=5,
                        category="prewarn",
                        ttl=5,
                        cooldown=3,
                    )
                self.prewarn = True
            else:
                self.speech.cancel("prewarn")
                if self.prewarn and not self.alarm:
                    self.speech.say(
                        "warning-cleared",
                        "Item scan matched. Warning cleared.",
                        priority=5,
                        ttl=5,
                    )
                self.prewarn = False

    def serial(self, m, *, enrolling=False):
        with self.lock:
            self._serial(m, enrolling=enrolling)

    def _serial(self, m, *, enrolling=False):
        t = m["t"]
        if t == "BOOT":
            if self.boot is not None and self.boot != m.get("bid"):
                self.speech.cancel("alarm")
                self.speech.cancel("prewarn")
                self.alarm = self.prewarn = False
            self.seen_feedback.clear()
            self.enrol_sequences.clear()
            self.boot = m.get("bid")
        elif t == "SCAN" and enrolling:
            self.enrol_sequences.add(m["seq"])
            if len(self.enrol_sequences) > 256:
                self.enrol_sequences.pop()
        elif t == "FB":
            identity = (self.boot, m["seq"])
            if identity in self.seen_feedback:
                return
            self.seen_feedback.append(identity)
            captured = m["seq"] in self.enrol_sequences
            self.enrol_sequences.discard(m["seq"])
            text = (
                "Tag captured. Save it to complete enrolment."
                if captured
                else {
                    "IN": "Access granted. Welcome.",
                    "OUT": "Checked out. Goodbye.",
                    "ISS": "Permission granted. Item issued.",
                    "RET": "Item returned. Thank you.",
                    "DEN": "Permission denied.",
                    "PRM": "Permission denied. Check the reader and your clearance.",
                    "NSS": "Scan your badge before scanning an item.",
                }.get(m["r"])
            )
            if text:
                self.speech.say(
                    f"feedback:{self.boot}:{m['seq']}",
                    text,
                    category="access",
                    cooldown=0,
                )
        elif t == "ALARM":
            self._alarm(m["why"])
        elif t == "ALARM_OFF":
            self.speech.cancel("alarm")
            self.speech.cancel("prewarn")
            if self.alarm:
                self.speech.say(
                    "alarm-ended",
                    "Alarm acknowledged."
                    if m["by"] in {"ACK", "BTN"}
                    else "Alarm sound stopped. Please review the incident.",
                    priority=5,
                    ttl=8,
                    cooldown=0,
                )
            self.alarm = self.prewarn = False

    def event(self, kind, payload):
        with self.lock:
            self._event(kind, payload)

    def _event(self, kind, payload):
        if kind == "CAMERA_HEALTH" and self.speech.c.tts_health_announcements:
            camera, state = payload["camera"], payload["status"]
            previous = self.cameras.get(camera)
            self.cameras[camera] = state
            if previous is None or previous == state:
                return
            label = "Phone shelf camera" if camera == "shelf" else "Laptop camera"
            phrase = {
                "OK": "is connected.",
                "OFFLINE": "is offline. Check its connection.",
                "COVERED": "is covered. Shelf monitoring is unavailable.",
                "MOVED": "needs alignment. Check shelf calibration.",
            }.get(state)
            if phrase:
                self.speech.say(
                    f"camera:{camera}:{state}",
                    label + " " + phrase,
                    priority=10,
                    ttl=6,
                    cooldown=30,
                )
        elif kind == "SERIAL_HEALTH" and self.speech.c.tts_health_announcements:
            self.speech.say(
                "serial:" + str(payload["connected"]),
                "Gate controller connected."
                if payload["connected"]
                else "Gate controller disconnected. Check the USB connection.",
                priority=10,
                ttl=6,
                cooldown=15,
            )
        elif kind == "SESSION_EXPIRED":
            self.speech.say(
                "session-expired",
                "An access session expired. Scan your badge to check in again.",
                ttl=6,
                cooldown=10,
            )
        elif kind in {"INCIDENT", "RECONCILIATION"}:
            verdict = payload.get("kind", payload.get("verdict"))
            phrase = {
                "OVERDUE": "An item loan is overdue.",
                "RETURN_UNSCANNED": "Item replaced without a return scan.",
                "RETURN_NOT_OBSERVED": "Return registered. Please place the item back on its shelf.",
                "ZONE_PERMISSION": "This shelf zone requires permission.",
            }.get(verdict)
            if phrase:
                self.speech.say(
                    "incident:" + verdict,
                    phrase,
                    priority=10,
                    ttl=8,
                    cooldown=20,
                )
