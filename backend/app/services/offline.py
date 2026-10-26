"""Low-priority whitelist synchronization and commit-before-ACK offline replay."""

import json
import logging
import threading
import time
from app.services.protocol import fnv1a, whitelist_messages
from app.db.models import OfflineRecord, SecurityEvent

log = logging.getLogger(__name__)


class OfflineCoordinator:
    def __init__(
        self,
        store,
        link,
        entries,
        board_id="gate-0",
        clock=time.monotonic,
        wall_clock=time.time,
    ):
        self.clock, self.wall_clock = clock, wall_clock
        self.store, self.link, self.entries, self.board_id = (
            store,
            link,
            entries,
            board_id,
        )
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        self.generation = 1
        self.sent_generation = 0
        self.active_generation = 0
        self.state = "WAITING_BOOT"
        self.error = None
        self.count = 0
        self.pending_replay = 0
        self.compatible = False
        self.retry_at = 0.0
        self.deadline = 0.0
        self.attempts = 0

    def request(self):
        with self.lock:
            self.generation += 1
            self.attempts = 0

            self.state = "QUEUED" if self.compatible else "WAITING_BOOT"
            self.error = None
            self.retry_at = 0.0

    def on_message(self, m):
        """Reader-thread hook: RAM updates only; never database or camera work."""
        with self.lock:
            if m["t"] == "BOOT":
                self.compatible = tuple(map(int, m["fw"].split("."))) >= (2, 0)
                self.sent_generation = 0
                self.active_generation = 0
                self.state = "QUEUED" if self.compatible else "INCOMPATIBLE"
                self.attempts = 0
            elif m["t"] == "HB":
                self.pending_replay = m["off"]
            elif m["t"] == "OFF":
                self.pending_replay = max(1, self.pending_replay)
            elif m["t"] == "WLOK" and self.active_generation:
                if m["n"] == self.count:
                    self.sent_generation = self.active_generation
                    self.active_generation = 0
                    self.state = "CURRENT"
                    self.error = None
                    self.attempts = 0
                else:
                    self.fail("COUNT")
            elif m["t"] == "WLERR" and self.active_generation:
                self.fail(m["why"])

    def fail(self, why):
        self.active_generation = 0
        self.error = why
        self.state = "QUEUED" if self.attempts < 3 else "FAILED"
        self.retry_at = self.clock() + 2

    def step(self):
        with self.lock:
            if not self.compatible or not self.link.connected:
                return
            if self.pending_replay:
                self.state = "AWAITING_REPLAY"
                return
            if self.active_generation:
                if self.clock() > self.deadline:
                    self.fail("TIMEOUT")
                return
            if (
                self.sent_generation == self.generation
                or self.state == "FAILED"
                or self.clock() < self.retry_at
            ):
                return
            generation = self.generation
            try:
                messages = whitelist_messages(self.entries())
            except ValueError as exc:
                self.state = "FAILED"
                self.error = str(exc)
                return
            self.active_generation = generation
            self.count = messages[0]["n"]
            self.state = "SENDING"
            self.attempts += 1
            self.deadline = self.clock() + len(messages) * 0.04 + 8
        for message in messages:
            with self.lock:
                if self.active_generation != generation:
                    return
            self.link.send(message)
            # One line per 40 ms leaves time for the RC522's bounded SPI polling.
            if self.stop.wait(0.04):
                return

    def replay(self, m):
        key = (self.board_id, m["bid"], m["id"])
        with self.store.session() as s:
            existing = s.get(OfflineRecord, key)
            if existing:
                if existing.uid_hash != m["h"] or existing.event != m["e"]:
                    raise ValueError(
                        "Offline replay identity reused with different payload"
                    )
            else:
                observed = self.wall_clock() - m["ago"]
                s.add(
                    OfflineRecord(
                        board_id=self.board_id,
                        boot_id=m["bid"],
                        event_id=m["id"],
                        uid_hash=m["h"],
                        event=m["e"],
                        observed_ts=observed,
                        received_ts=self.wall_clock(),
                    )
                )
                s.add(
                    SecurityEvent(
                        type="OFFLINE_EVENT",
                        severity="WARNING" if m["e"] == "DEN" else "INFO",
                        payload_json=json.dumps(
                            m | {"observed_ts": observed, "board_id": self.board_id}
                        ),
                    )
                )
        self.link.send({"t": "OFFOK", "id": m["id"]})

    def start(self):
        self.thread = threading.Thread(
            target=self.run, daemon=True, name="whitelist-sync"
        )
        self.thread.start()

    def run(self):
        while not self.stop.is_set():
            try:
                self.step()
            except Exception:
                log.exception("Whitelist synchronization failed")
            self.stop.wait(0.1)

    def status(self):
        with self.lock:
            return {
                "state": self.state,
                "error": self.error,
                "count": self.count,
                "pending_replay": self.pending_replay,
            }

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(2)


def badge_entries(engine):
    with engine.auth_lock:
        entries = [
            (fnv1a(uid), p.get("level", 1), False)
            for uid, p in sorted(engine.whitelist.items())
        ]
        entries += [
            (fnv1a(uid), p["min_level"], True)
            for uid, p in sorted(getattr(engine, "items", {}).items())
        ]
    if len({h for h, _, _ in entries}) != len(entries):
        raise ValueError(
            "UID hash collision: change the conflicting tag before offline sync"
        )
    return entries
