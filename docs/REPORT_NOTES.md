# Report notes: seven EDLC phases

**Current operational additions (2026-10-27):** the user resumed beyond M2. Specification binds physical badge reader D10/D9 and item reader D4/D5, gate-only three-failure photos and phone shelf observation. Partitioning keeps serial/RAM authorization and UNO deadlines independent from SQL/capture/provider work. Design adds TTL session states, level/zone permissions, issue/return ledger, reconciliation (MATCHED/LATE_MATCH/denied/unissued/return exceptions), learned anchor transforms and reveal/empty-reference classification. Implementation upgrades SQLite additively, buffers detection-time evidence in RAM, adds an independent Telegram queue and extends dashboard controls/history. Integration uses protocol 2.0 with firmware 2.1 and compiles all four variants. Testing combines injected-time operational scenarios with ten original threaded regressions, real ArUco on synthetic frames, API/auth checks and mocked providers. Maintenance exposes failed durable queues, firmware incompatibility, camera health, cache sync and delivery statuses. OPERATIONAL_VERIFICATION.md records current software evidence; HUMAN_TODO.md orders real checks. Optional people sensing, LCD and ultrasonic remain absent. The M2 paragraph below is historical.

**v2 M2 additions:** specifications now separate declared RFID authorization from observed motion, with the reconciliation/ledger implementation explicitly deferred to M3/M4. Partitioning adds EEPROM offline policy, a local prewarning/dead-man timer, debounced button and hardware watchdog to the UNO. Detailed design uses result-coded AUTH/FB, session-count mirroring, table-driven PROGMEM patterns, telemetry and two alternating reader polls. Integration includes count/CRC-validated whitelist staging and durable replay ACKs. Testing compiles four main variants/six unit sketches, injects clocks for local deadlines/offline logic and checks replay/DB-failure isolation; real GPIO/WDT/power/shared-SPI results remain blank for the student. Maintenance adds boot-ID journaling, wear-conscious EEPROM.update and explicit cache-revocation verification. Use V2_VERIFICATION and MEASUREMENTS for actual evidence; do not describe the M3–M8 features as built.

Use these as source notes, not as invented experimental results. Add your hardware photos, measured timings and observations from TEST_PLAN.

## 1. Specifications

- Problem: identify warehouse workers, attribute inventory movement during an authorized session, and detect unattended removal or repeated failed access.
- Inputs: 13.56 MHz RFID UID, gate webcam, shelf MJPEG frames, operator acknowledgement.
- Outputs: green/red LEDs, buzzer pattern, database events/incidents, evidence and WhatsApp alerts.
- Constraints: UNO ATmega328P has 2 KB SRAM; fixed 96-byte serial lines, no heap String/ArduinoJson, nonblocking timers; reader supply/logic 3.3 V; laptop performs vision/network tasks.
- Acceptance: software tests/build, real firmware compile/upload, local alarm independence, calibrated vision, and human-verified delivery/latency.

## 2. Hardware/software partitioning

- UNO: RFID acquisition, matching pending AUTH sequence, session toggle, 60-second failure window, 30-second alarm, 6-second PC watchdog, local output timing.
- Laptop: whitelist cache, serial reconnect/heartbeat, sessions/history, image capture, ArUco/ROI voting, evidence, notification retries, admin dashboard.
- Phone: stable streaming camera; no security decision on the phone. Twilio: external delivery only; never in the local alarm dependency path.
- Justification: deterministic local outputs stay small and independent; memory/network/image workloads belong on the laptop.

## 3. Iterations

- M1 bounded protocol and executable firmware simulator; M2 DB/rules; M3 gate capture; M4 notifier and signing; M5 vision/health; M6 shelf evidence; M7 UI; M8 firmware/hardware tools; M9 documentation and integration.
- Refined classification from “marker missing” to PRESENT/ABSENT/OCCLUDED using an empty reference to avoid treating a hand as removal.
- Isolated AUTH and REMOVAL dispatch ahead of durable/camera operations. Camera/notifier failures create diagnostics without inhibiting UNO alarm behavior.
- Verified official OpenCV API variants, Twilio service-window error and request signatures, and MFRC522 usage. See DECISIONS and VERIFICATION for actual revisions and results.

## 4. Detailed design

Gate states:

```text
SESSION OUT --valid card A--> IN(A) --valid A--> OUT
IN(A) --valid B--> BUSY (stays IN A)
SCAN --AUTH deny / 1 s timeout--> FAIL(red 2 s)
FAIL x3 in first-fail 60 s window --> ALARM; counter=0
any valid scan / window expiry --> counter=0
OUT + REMOVAL --> ALARM(SHELF_BREACH)
IN + REMOVAL --> no alarm
ALARM --ACK / 30 s--> quiet
no PC HB 6 s --> PC_LOST LED alternation; HB --> recovered
```

Shelf states:

```text
marker center in ROI -> PRESENT vote
no marker + blurred ROI resembles empty reference -> ABSENT vote
no marker + nonempty difference -> OCCLUDED vote
no reference or unreliable camera -> UNKNOWN vote
4 agreeing votes out of last 5 -> state change
ABSENT + worker -> attributed event
ABSENT + no worker -> REMOVAL + incident/evidence/alert
OCCLUDED >2 s + no worker -> warning only
return to PRESENT after absent/occluded + no worker -> warning
```

Protocol summary (complete examples/fields in PROTOCOL.md):

| Direction | Messages | Purpose |
|---|---|---|
| UNO -> PC | BOOT, SCAN, SESSION, FAIL, BUSY, ALARM, ALARM_OFF, HB | Gate events/state and health |
| PC -> UNO | AUTH, REMOVAL, ACK, HB, SYNC, CFG, TEST, ALARM | Authorization, shelf input, control, recovery |
| Framing | 115200 8N1, LF JSON, <=96 bytes, uppercase UID | Bounded parsing and serial interoperability |

- Debounce and millis timers reject repeated reads and transient frames. Fixed buffers keep UNO SRAM predictable.
- SHA-256 per saved file; text/media notification rows separately track attempts/SIDs/status.
- Authenticated REST/WS plus expiring public JPEG tokens; SQLite WAL transactions and indexes support a single hardware process.
- See SCHEMA for tables and DESIGN for UI decisions.

## 5. Integration

- Upload unit sketches before main firmware. Confirm BOOT/HB and real protocol conformance before connecting the dashboard.
- Enrol actual UIDs; ensure simulation data does not authorize real cards. Mount camera/markers, calibrate ROIs and empty references, then test shelf events.
- Add Twilio last: join sandbox, configure HTTPS callbacks, validate inbound timer, test text and photo. The alarm remains functional if this service is unavailable.
- Verify persisted open sessions are restored by SYNC after backend or board restart. Record actual observed reset behavior.

## 6. Testing

- Automated: protocol invalid-input cases, simulator clocks, classifier images, debounce/health, rules, notifications/retries/signatures, signed URLs, API and full scenario list.
- Hardware: voltage/wiring checks, UID/output sketches, interactive self-test and protocol script, disconnect tests, real evidence and delivery.
- Performance: instrument electrical edges, compute median/p95 from real timestamps; label whether measurement includes camera/debounce delay. Do not equate simulated state changes with physical LED/buzzer timing.
- Failure tests: no phone stream, covered lens, moved anchors, lost heartbeats, failed camera/notifier, expired media/session, and restart with an open worker.
- Fill blank worksheet columns with measured results and link screenshots/raw traces. Separate verified software from unverified hardware.

## 7. Maintenance

- Recalibrate after camera/lighting changes; inspect mounting and wires, reopen WhatsApp session before demos, rejoin sandbox membership when necessary.
- Retention defaults 30 days; Keep preserves important originals. Stop and back up DB/media together. Do not publish evidence or secrets.
- Pin dependencies and firmware library/core versions; rerun automated tests/build and physical checks after upgrades. Schema migration support is future work.
- Limitations: UID cloning, visual occlusion/lighting ambiguity, single gate/worker/camera, no production lock control, no approved out-of-session WhatsApp templates. See DECISIONS/VERIFICATION for the final scope.
