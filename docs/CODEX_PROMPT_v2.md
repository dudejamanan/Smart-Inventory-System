# CODEX PROMPT v2: Smart Warehouse "Declared vs Observed" iteration

## 0. ROLE AND WORKING RULES
You are continuing an existing repository (v1 is delivered and described in README.md, AGENTS.md, docs/DECISIONS.md, docs/VERIFICATION.md). Work autonomously, do not ask questions, record every decision in `docs/DECISIONS.md`.

Before changing anything: read AGENTS.md, docs/PROTOCOL.md, docs/ARCHITECTURE.md, firmware/arduino_gate/*, backend/app/{runtime.py,main.py,config.py}, backend/app/services/{engine,vision,serial_link,notifier,evidence,capture,frames}.py, backend/app/sim/arduino.py, backend/app/db/models.py, backend/tests/*, tools/*. Run the existing tests and record the baseline. Then `git tag v1.0` and work on branch `v2`.

Rules that still apply from v1:
1. Do every software task end to end (firmware, backend, frontend, simulator, tests, scripts, docs). Run tests and fix failures before reporting.
2. Anything needing real hardware, accounts, calibration or credentials goes to beginner-friendly numbered instructions in `docs/` and a checklist item in `docs/HUMAN_TODO.md`. The user is a student doing hardware in parallel.
3. Never invent results. Final report separates "verified (command + output)" from "not verified (and why)". Never claim hardware results from simulation.
4. Secrets only in `.env`; commit `.env.example`; pin dependency versions; type hints, logging, clear errors.
5. The alarm path must NEVER depend on notifications, the database, or any camera. Keep AUTH dispatch isolation (decision 19 in DECISIONS.md).
6. Firmware: no `String`, no ArduinoJson, no `delay()`, no dynamic allocation, fixed buffers, `F()`, `millis()` timers with unsigned subtraction, max 96 bytes per serial line.
7. Do not delete or weaken tests to make them pass. If v2 intentionally changes behaviour, update the test and explain why in DECISIONS.md.
8. Commit after each milestone. Keep the full pytest run under about 90 s (use injected clocks, not sleeps, for new logic).

## 1. WHY v2 (review findings to fix)
| ID | Finding in v1 | Fix required |
|---|---|---|
| F1 | `engine.slot_change`: any removal while a session is open is only logged. Tailgater or restricted-item taker raises no alarm. | Removal must match an ISSUE transaction for that item (R-RECON). |
| F2 | One global session, no expiry, BUSY for a second worker; stale session restored from DB on restart. | Multiple sessions with automatic expiry (R-SESS). |
| F3 | No ledger, no item identity by RFID, zones are warning-only and off. | Item tags, clearance levels, issue/return ledger, due dates (R-LEDGER). |
| F4 | Whitelist only on PC. PC lost means every tap times out, counts as failure, third tap alarms. | EEPROM whitelist and offline mode (R-OFFLINE). |
| F5 | Camera is the single fragile source: marker can be peeled and left; empty-reference diff depends on lighting; phone angle must match calibrated ROIs. | Anchor markers, reveal markers, learn-shelf calibration (R-VISION). |
| F6 | Arduino has little embedded depth. | EEPROM, watchdog, dead-man timer, button, telemetry, optional second reader (R-FW). |
| F7 | Twilio sandbox is fragile for demos. | Add Telegram notifier, keep WhatsApp optional (R-NOTIFY). |

## 2. CONCEPT
Authorization is **declared** by RFID scans (person badge, item tag). Reality is **observed** by cameras. The engine reconciles the two and alarms on mismatch. The Arduino owns instant feedback, the offline whitelist, the grace (entry-delay) timer and the alarm. The PC owns ledger, rules, vision, evidence, alerts and dashboard.

Primary use case in docs: college lab component store. Also document library, tool crib and pharmacy cabinet profiles in `docs/USE_CASES.md`.

## 3. REQUIREMENTS

### R-FW: Firmware v2 (`firmware/arduino_gate`, fw "2.0")
Pin map in `config.h` (keep v1 pins):
- Reader 0: SS=D10, RST=D9. Reader 1 (optional, `READER_COUNT 2`): SS=D5, RST=D3. Shared SCK=D13, MOSI=D11, MISO=D12. RC522 at 3.3 V.
- Buzzer D6 (`BUZZER_ACTIVE` flag, `tone()` for passive). Green D7, red D8. Button D4 (`INPUT_PULLUP`, 30 ms debounce, short and long press).
- Reserved and documented: A1/A2 HC-SR04, A4/A5 I2C LCD. Do not implement unless M9.

Behaviour:
1. **Result-coded AUTH.** After SCAN the PC replies `{"t":"AUTH","seq":N,"r":"IN|OUT|ISS|RET|DEN|PRM|NSS","n":sessions}`. The board maps the code to feedback with a table-driven pattern list (document the table in PROTOCOL.md):
   - IN: green steady while n>0, short beep. OUT: two green blinks, two short beeps. ISS: three fast green blinks, one beep. RET: two slow green blinks, one beep.
   - DEN (unknown or inactive) and NSS (item tap with no session): red 2 s, counts as a failure. PRM (no permission): red 2 s, two beeps, does NOT count toward the gate alarm.
   - Any success resets the failure counter. Fail counter semantics, window and alarm as in v1 (default 3 in 60 s, alarm 30 s).
2. **No BUSY, no local session toggling.** The board only tracks `n` (open session count, sent in AUTH and HB) for the green LED.
3. **Grace / dead-man timer.** PC sends `{"t":"PW","on":1,"s":10}`: red blinks 1 Hz and buzzer chirps 80 ms each second. `{"t":"PW","on":0}` cancels. If not cancelled within `s` seconds, **the board escalates by itself** to ALARM `SHELF_BREACH` (also emits `{"t":"ALARM","why":"DEADMAN"}`). This must work with the PC dead.
4. **Alarm patterns by reason**: `GATE_3_FAIL` (200 ms on/off), `SHELF_BREACH` (600 ms on, 300 ms off), `PC_CMD`. Red fast blink during any alarm. Alarm stops on timeout, `ACK`, or button long press (`by:"BTN"`; compile flag `BTN_ACK_ENABLED`). Short press mutes the buzzer for 30 s only.
5. **EEPROM whitelist** (R-OFFLINE below).
6. **Hardware watchdog**: `USE_WDT` (default 1), 2 s, reset in loop; capture MCUSR early (avr-libc `.init3` pattern) and report in BOOT `{"t":"BOOT","fw":"2.0","rst":"PWR|EXT|BOR|WDT","rd":1}`. Provide `firmware/tests/wdt_test.ino` that deliberately hangs and proves the reset. Document that a clone with an old bootloader may boot-loop and how to set `USE_WDT 0`.
7. **Telemetry**: HB every 2 s `{"t":"HB","up":N,"n":1,"pcok":1,"ram":1432,"lp":1840,"off":0}` (free RAM bytes, max loop time in microseconds since last HB, offline events pending). Also `{"t":"FB","seq":12,"r":"IN","ms":37}` after feedback starts (ms from SCAN to output) for latency evidence.
8. **Two readers**: poll alternately; `rd` field in SCAN; per-reader 1.5 s card debounce; works with `READER_COUNT 1` unchanged.
9. PC watchdog as in v1 (no HB 6 s = PC_LOST). In PC_LOST the board stays usable (offline mode), idle LEDs alternate slowly.
10. Budgets: global RAM at most 1100 B, flash under 24 KB, report `arduino-cli compile` output for active/passive buzzer and `READER_COUNT` 1/2. Comment every non-obvious block for a beginner.
11. New sketches in `firmware/tests/`: `button_test.ino`, `wdt_test.ino`, `eeprom_test.ino`, `two_reader_test.ino` (keep `rfid_test`, `led_buzzer_test`).

### R-PROTO: Protocol v2 (`docs/PROTOCOL.md`, `services/protocol.py`)
Arduino to PC: `BOOT`, `SCAN{uid,seq,rd}`, `FAIL{uid,n,why:DENY|TIMEOUT|NSS}`, `FB`, `ALARM{why:GATE_3_FAIL|SHELF_BREACH|DEADMAN|PC_CMD}`, `ALARM_OFF{by:TIMEOUT|ACK|BTN}`, `PW{st:ON|OFF|ESC}`, `HB`, `BTN{k:S|L}`, `OFF{id,h,e:IN|OUT|ISS|DEN,ago}`, `WLOK{n}`, `WLERR{why}`.
PC to Arduino: `AUTH`, `PW`, `ALARM{on,why}`, `ACK`, `HB{n}`, `CFG`, `TEST`, `SYNC{n}`, `WL{op:CLR|ADD|END,h,lv,it,n,ck}`, `OFFOK{id}`.
UID hash used on the wire and in EEPROM: FNV-1a 32-bit over the uppercase hex UID characters, printed as 8 hex digits. Implement identically in C++ and Python and test it with shared vectors.
Backend must reject `fw` below 2.0 with a clear dashboard banner. Update the SimulatedArduino as an exact executable spec (injected clock) and keep `tools/protocol_conformance.py` working for simulator and real board.

### R-SESS: Sessions
Multiple concurrent sessions (`MAX_SESSIONS=4`). Remove the single-open-session unique index. Session TTL `SESSION_TTL_MIN=30`, renewed by any successful scan of that person; expiry closes the session (`end_reason=EXPIRED`), emits an event and updates the board count. A badge tap by a person with an open session checks out. On restart, restore only sessions not yet expired. Attribution: an item tap belongs to the most recent badge tap within `ATTRIBUTION_WINDOW_S=30`, else to the sole open session, else result NSS.

### R-LEDGER: Items, permissions, ledger
- `personnel`: add `level` (1 to 3, default 1). `inventory_items`: add `tag_uid` (unique, nullable), `min_level`, `loan_minutes`, `status` (AVAILABLE, ISSUED, MISSING), `holder_id`, `due_ts`. Keep zones: when `ZONES_ENABLED`, permission = level ok AND zone ok.
- New `transactions`(id, ts, kind ISSUE|RETURN|RETURN_OTHER|DENIED, personnel_id, item_id, session_id, reader, seq, due_ts, note) and `reconciliations`(id, ts, slot_id, item_id, observed_ts, tx_id, verdict MATCHED|LATE_MATCH|UNISSUED|DENIED_REMOVAL|NO_SESSION|RETURN_UNSCANNED, delta_ms, incident_id).
- Tag registry: a UID is a badge or an item tag (unique across both). Dashboard "enrol next scanned tag" for both.
- Overdue job every `OVERDUE_CHECK_S=30`: WARNING incident `OVERDUE` once per item and notification (rate-limited).
- CSV export `GET /api/ledger.csv`. Demo seed (simulation only): Aarav level 2, Meera level 1, items Resistor Kit (L1), Multimeter (L2), Raspberry Pi (L3) with a 2 minute loan for the overdue demo. Real mode starts blank.
- Schema: bump version, recreate-on-fresh-install is acceptable; add `scripts/reset_db` and document. Update `docs/SCHEMA.md`.

### R-RECON: Reconciliation engine (`services/reconcile.py`, injected clock)
Settings: `REMOVAL_POLICY=strict_issue|session_lenient` (v1 behaviour), `REMOVAL_GRACE_S=10`, `ISSUE_TOKEN_TTL_S=30`, `RETURN_GRACE_S=20`, `RETURN_PLACE_S=60`.
On debounced slot ABSENT at t0, in order:
1. ISSUE transaction for that item with ts >= t0 - ISSUE_TOKEN_TTL_S, not yet consumed: verdict MATCHED, consume it, no alarm.
2. DENIED transaction for that item within the TTL: immediate incident `DENIED_REMOVAL` CRITICAL and `ALARM{on:1,why:SHELF_BREACH}`.
3. No open sessions: immediate `UNISSUED_REMOVAL` CRITICAL and alarm.
4. Otherwise send `PW{on:1,s:REMOVAL_GRACE_S}`. If an ISSUE for that item arrives in time: LATE_MATCH, send `PW{on:0}`. If not: incident `UNISSUED_REMOVAL` CRITICAL listing who was inside, send the alarm, request evidence and notifications.
On slot PRESENT after ABSENT: if the item is ISSUED and no RETURN arrives within `RETURN_GRACE_S`, WARNING `RETURN_UNSCANNED`. A RETURN tap while the slot is still ABSENT expects PRESENT within `RETURN_PLACE_S`, else WARNING `RETURN_NOT_OBSERVED`. If the shelf camera is OFFLINE, COVERED or MOVED, reconciliation shows a banner and the ledger keeps working. Every verdict is stored in `reconciliations` and pushed on the WebSocket.
`session_lenient` must reproduce v1 behaviour and keep the old tests meaningful.

### R-VISION: Shelf vision upgrade
- Marker ranges (DICT_4X4_50): items 0 to 19, reveal markers 20 to 39 (marker 20+n sits behind item n), anchors 40 to 49.
- `SLOT_MODE=reveal|empty_ref|both` (default both). Slot state: item marker at its learned resting position gives PRESENT; else reveal marker visible gives ABSENT; else if empty reference matches (when available) ABSENT; else OCCLUDED. Keep debounce and camera health.
- With at least 3 anchors visible compute a homography to a canonical shelf plane (`SHELF_RECT_W`, `SHELF_RECT_H`), store slot rest positions in canonical coordinates, so moving the phone slightly does not need recalibration. Fewer than 3 anchors: fall back to pixel ROIs and report MOVED health as in v1.
- Calibration API and UI: "Learn shelf" button (all items present, learns rest positions and reveal markers visible when you remove each box, guided one slot at a time), rectified live view, anchor residual display.
- Update `SyntheticShelfSource` to draw reveal markers and anchors, and to support a simulated camera pose change.

### R-NOTIFY: Notifications
Keep the Notifier interface and Twilio WhatsApp. Add `TelegramNotifier`: `sendMessage` and `sendPhoto` by multipart upload (no public URL needed), retries with backoff, per-kind 20 s rate limit, `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`. `NOTIFY_CHANNELS=telegram,whatsapp` (use those configured; mock when none). Delivery status in `notifications`. Tests with mocked httpx. `tools/telegram_test.py`, `docs/TELEGRAM_SETUP.md` (BotFather, getting chat id, privacy). Notifier failure never affects buzzer, logging or evidence.

### R-OFFLINE: EEPROM whitelist and offline mode
- Layout: magic, version, count, entries of 5 bytes (hash32 + flags: bits 0-1 level, bit 7 is-item), CRC16, up to 100 entries. Use `EEPROM.update` and write only on `WL END` after a valid count and checksum.
- On connect and on any personnel or item change the PC sends `WL CLR`, `WL ADD`..., `WL END`. Board answers `WLOK` or `WLERR`.
- When PC is lost: authorize badges from EEPROM locally (IN/OUT using an in-RAM set of up to 8 hashes), count failures and alarm as usual, accept item taps if an attributed badge has sufficient level; log events in a 16-entry RAM ring and replay them as `OFF` messages on reconnect with `OFFOK` acknowledgement (at-least-once; PC deduplicates by boot id and id). Shelf alarms are unavailable offline; document this limitation. Simulator and tests cover it.

### R-PERSON (milestone M7, optional): Gate person counting
`PersonDetector` interface with `YoloOnnxDetector` (YOLOv8n ONNX via `cv2.dnn`, model file in `models/`, gitignored; `tools/export_person_model.py` exports it using ultralytics on a dev machine; note the AGPL license in DECISIONS.md), `HogDetector` fallback and `SyntheticDetector` for tests. `PERSON_DETECTION=off|auto|on`, `PERSON_FPS=3`. Rule `TAILGATE_SUSPECT`: at a valid IN scan, if max people count over scan time and `TAILGATE_WINDOW_S=5` is at least 2, create a WARNING incident with the gate photo. Optional `UNBADGED_PRESENCE` (default false, with a configurable zone ROI, `UNBADGED_S=8`): person in zone with no open session and no valid scan in `ENTRY_WINDOW_S` creates a WARNING incident and a chirp; warn in docs that the laptop user in view causes false positives. If the model is missing, disable cleanly with a dashboard note.

### R-UI: Dashboard
Split `frontend/src/main.tsx` into modules/components. Pages: Live (open sessions with countdown, slot cards, PREWARN and alarm banner, live reconciliation feed), Ledger (holders, history, overdue, CSV button), Incidents (with a reconciliation timeline: declared event vs observed event and delta), People and Items (level, tag enrolment), Calibration (rectified view, anchors, learn shelf), Settings, Health (serial, cameras, notifier channels, firmware telemetry: free RAM, max loop time, last reset cause, offline queue). Simulation panel gets buttons for each new scenario. `npm run build` must pass; add a few component or logic tests if cheap.

### R-TOOLS and R-DOCS
- Update `tools/hw_selftest.py` (button, second reader, EEPROM round trip, telemetry), `tools/protocol_conformance.py`, `tools/latency_bench.py` (use `FB` ms plus optional slow-motion frame-count input), `tools/print_markers.py` (items 0-19, reveal 20-39, anchors 40-49, label sheets).
- New or updated docs: ARCHITECTURE, PROTOCOL v2, SCHEMA, HARDWARE_GUIDE (1-reader and 2-reader wiring with six dividers, 3.3 V power budget and external supply for two readers, buzzer transistor stage, button, optional LCD), PHONE_CAMERA_SETUP (hotspot approach because campus Wi-Fi may isolate clients), CALIBRATION_GUIDE (learn shelf), TELEGRAM_SETUP, USE_CASES, SECURITY_NOTES (cloned UIDs, replay, serial spoofing, tailgating, marker spoofing, privacy), DEMO_SCRIPT (the 10-step demo: authorized entry, intruder x3, legal issue, permission denied, unscanned removal while someone is inside, return, laptop off offline mode, camera covered, close), MEASUREMENTS (how to collect each number and blank tables), TEST_PLAN, REPORT_NOTES (map to the 7 EDLC phases, state machines, partitioning rationale), HUMAN_TODO split into "while Codex works" and "after".

## 4. TESTS (all must pass)
Protocol parser (new messages, oversized, duplicates); shared FNV-1a vectors; firmware port: result-coded feedback, fail counter rules (PRM not counted), dead-man escalation with PC silent, button, watchdog flag logic where testable, offline mode and replay dedup; sessions (concurrent, expiry, attribution); ledger and permissions; reconciliation (matched, late match, unscanned, denied then removal, nobody inside, return flows, camera unhealthy); overdue; vision (reveal, anchors homography with simulated pose change, fallback); Telegram notifier mocked with retry and rate limit; API endpoints (CSV); alarm isolation with DB, notifier and cameras failing.
`tools/fake_scenarios.py` must run at least these end-to-end scenarios and print a PASS table: valid entry; unknown once; unknown three times; two sessions at once; session expiry; issue then lift (matched); lift then late scan (late match); lift with no scan while someone is inside (grace then alarm); permission denied then lift (immediate alarm); lift with nobody inside; return flow; overdue; hand occlusion; camera covered; camera pose shift handled by anchors; serial disconnect with offline authorization and replay; restart with restored sessions; notifier down while alarm still sounds; (if M7) tailgate suspect with synthetic detector.

## 5. MILESTONES (commit after each; stop and report after M2)
- M0: baseline audit and `docs/V2_CHANGES.md`, no behaviour change.
- M1: protocol v2, SimulatedArduino v2, firmware core (result-coded AUTH, PW/dead-man, patterns, button, telemetry, WDT), conformance tool, test sketches. Compile for active/passive and `READER_COUNT` 1/2.
- M2: EEPROM whitelist, offline mode, offline log replay (firmware, simulator, backend). **Stop here and report so the user can flash and test on hardware.**
- M3: data model v2, sessions, ledger, permissions, overdue, API and CSV.
- M4: reconciliation engine and scenario tests.
- M5: Telegram notifier and mock tests.
- M6: vision upgrade (reveal, anchors, learn shelf).
- M7: person detector and tailgate rule (optional, behind flags).
- M8: dashboard v2, docs, hardware guide, demo script, measurement sheets, final polish.
- M9 (only if all else passes): I2C LCD messages and HC-SR04 approach sensing, both behind flags.

## 6. ACCEPTANCE
Full pytest passes; frontend builds; `python -m app --simulate` runs the whole scenario list; firmware compiles (report flash and RAM for each variant); no secrets or runtime data tracked; the alarm path works with Telegram, WhatsApp, database and both cameras failing; all docs listed above exist and match the code.

## 7. FINAL REPORT
1. What changed (short). 2. Verified, with commands and output. 3. Not verified and why. 4. Decisions and assumptions. 5. Known limitations. 6. What the user must do next, in order, pointing to `docs/HUMAN_TODO.md`.
