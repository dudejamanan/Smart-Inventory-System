# Architecture: current operational build

The 2026-10-27 request resumes development beyond M2. Physical reader #1 (wire rd=0, D10/D9) handles badges; reader #2 (rd=1, D4/D5) handles items. Firmware 2.1 retains protocol 2.0, disables the absent button and confines gate-failure counting to rd=0. Strict mode rejects old firmware. Four TTL sessions and tag/permission/item state are cached in Engine. Serial SCAN decisions and FB confirmation update RAM before SQL. A separate timer thread expires sessions and escalates unresolved removals without SQL/camera/provider calls. The event worker drains a bounded ordered queue; a failed head remains for retry, exposed in health.

SQLite's additive schema version 3 retains history. Transactions and reconciliations have idempotency tokens; each reconciliation and its incident commit together. Management refreshes RAM and EEPROM. Offline cached badges/items include levels, while replay remains commit-before-ACK and deliberately does not fabricate attributed loans.

Phone MJPEG feeds item/reveal detection, learned four-anchor homography (three-anchor affine fallback), voting and health supervision. Calibration pause suppresses new shelf rules while retaining gate feedback and already armed deadlines. Removal-time frames remain in bounded RAM through grace for evidence. The laptop webcam previews RAM frames; default saved gate photos occur only at GATE_3_FAIL. WhatsApp and optional Telegram run in separate notification workers. WhatsApp uses expiring signed backend JPEG URLs; Telegram uploads JPEG bytes. UI includes sessions, ledger, reconciliation, levels/tags and learn/pause controls. Optional person detection/LCD/ultrasonic are absent. See CURRENT_SETUP.md.

## Historical M2 architecture

The current delivery stops after firmware/protocol and EEPROM offline/replay integration. M3–M8 add the ledger, multiple TTL sessions, strict reconciliation, Telegram, learned/reveal/rectified vision and modular dashboard. The original design is preserved in ARCHITECTURE_V1.md and tag v1.0. The supplied v2 prompt is the roadmap, not a claim that every requirement has shipped.

```text
Reader 0 (+ optional Reader 1) -- SPI --> UNO fw 2.0
     EEPROM whitelist / offline badge set / 16-event RAM ring
     result-pattern outputs / PW dead-man / D4 button / hardware WDT
                         | bounded v2 JSON, 115200
                  serial reader + writer
                    | direct AUTH from RAM cache (no DB/camera wait)
                    | bounded event queue
                    v
           engine + temporary v1 session adapter --> SQLite WAL
                    |                             offline_records dedup
                    +--> evidence / notification workers
                    +--> authenticated REST + WebSocket --> React console

Low-priority whitelist coordinator --> paced CLR/ADD/END --> valid EEPROM commit
Offline OFF --> SQL record + event transaction --> COMMIT --> OFFOK
```

## Ownership and safety

Online AUTH carries a result code and authoritative session count. The UNO no longer toggles online sessions or emits BUSY. It owns feedback patterns, failure windows, alarm duration, button debounce/mute/ACK, the heartbeat watchdog and grace escalation. PW cannot be postponed by later PW starts; cancellation or acknowledgement is explicit. DEADMAN uses the shelf alarm pattern and needs no PC, camera, database or notifier once armed.

An EEPROM-valid offline badge is accepted locally when heartbeats stop. Offline item taps use an attributed badge's cached level, and log IN/OUT/ISS/DEN. This is not an audited item issue/return ledger. No new shelf observation exists without the PC camera/rules pipeline. A camera fault warns rather than fabricating an event.

AUTH uses its own whitelist-cache lock. A database-backed rules lock cannot delay it. Unattended shelf ALARM dispatch occurs before acquiring that lock. Calibrated v1 slot configuration/references are cached, so a database outage after loading cannot prevent an otherwise observed removal command. Database writes may still fail; the software logs the error rather than pretending history was stored.

## EEPROM, RAM budget and replay

One 500-byte union holds either 100 staged entries or the offline ring. Whitelist replacement waits until all offline records are acknowledged; it is rejected while authentication, alarm or PW is active. CLR/ADD stage only in RAM. END verifies count, unique hashes and CRC before EEPROM.update; magic is committed last. Identical valid uploads skip writes. An interrupted whitelist commit fails closed. Separate alternating boot-counter slots preserve the last valid counter across a torn counter update.

The ring never overwrites unacknowledged events. At 16 entries, new offline operations fail closed with FULL. Its records are volatile; power loss and board reset clear them and offline session identities. UNO serial auto-reset is a real hardware consideration: keep the port open and pause heartbeats for replay tests. EEPROM survives normal reset; a complete EEPROM erase/new physical board requires a new BOARD_ID when reusing a replay database.

OFF includes boot id and event id; the backend scopes uniqueness by configured BOARD_ID. It stores one offline_records row and one OFFLINE_EVENT in the same transaction and sends OFFOK only after commit. An interrupted/failed DB write leaves the record on the board for retry. Duplicate identical deliveries are acknowledged without duplicate history; conflicting reuse is rejected.

## Backend concurrency and lifecycle

One backend process owns the devices. Independent serial reader/writer, frame grabbers, vision, event processing, photo/evidence pools, notification worker and low-priority whitelist coordinator isolate I/O. Coordinator callbacks on the reader thread update RAM only. WL lines are paced at 40 ms to leave time for bounded RC522 SPI polling. SQLAlchemy sessions are short and never shared between threads. SQLite uses WAL, foreign keys and a busy timeout.

The coordinator runs on BOOT and registry changes, waits for replay to drain, retries bounded failures and shows CURRENT/SENDING/AWAITING_REPLAY/FAILED status. The M2 registry contains active badges at level 1; item tag/clearance fields arrive in M3. Changing an item currently requests resynchronization but cannot add a tag the current schema does not yet store.

Startup loads the existing single open session and mirrors its count. It does not yet expire old sessions or merge offline users into a multi-session ledger; those are M3 changes. The firmware below 2.0 is rejected for online authorization and shown as incompatible. Simulation uses the v2 board port, real OpenCV pipeline, SQL/API/evidence code, and a mock notifier unless credentials are deliberately set. Explicit v1 simulator/parser snapshots exist only for legacy regression tests.

Shutdown stops vision/whitelist/serial, drains event work, closes workers and releases sources/DB. An abrupt process kill can still lose unpersisted PC queues; OFF retry survives only while the board remains powered and unreset.

## Unchanged subsystems at this checkpoint

Vision is still marker-in-ROI plus blurred empty-reference difference with temporal voting and OFFLINE/COVERED/MOVED warnings. Anchor homography, reveal markers and Learn shelf arrive at M6. Current online removal policy is still session-lenient; a session is not proof of ownership. Strict transaction reconciliation is M4.

Gate capture selects the sharpest of three frames; shelf evidence stores T-2/T0/T+1 snapshots and a six-second resampled clip or JPEG fallback with SHA-256. Missing source history is padded with nearest real frames, not invented pre-event footage. Retention preserves Keep evidence and active calibration references.

Notifications remain the isolated v1 mock/Twilio queue, signed JPEG URLs, request-validated webhooks and session timer. Telegram is M5. Admin cookie/CSRF/origin protections remain; signed public media never grants general filesystem access. See SECURITY_NOTES for cloned UIDs, serial spoofing, replay and privacy limits.
