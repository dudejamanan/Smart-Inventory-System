# Test plan and real measurement worksheet

## Current supplied-circuit acceptance (2026-10-27)

Use CURRENT_SETUP.md and DEMO_SCRIPT.md. These are **blank physical measurements**, not simulated outcomes.

| Test | Expected | Actual | Pass/fail | Evidence |
|---|---|---|---|---|
| Firmware/wiring | fw 2.1, rd 2, physical #2 D4/D5, no button | | | |
| Reader roles | #1 badges IN/OUT, #2 items ISSUE/RETURN | | | |
| Gate one/two/three wrong badges | Logs only twice; third local alarm + one saved laptop photo | | | |
| Item-reader wrong tags | No gate threshold alarm | | | |
| Two sessions / expiry | Independent sessions and real configured TTL | | | |
| Permitted issue then lift | MATCHED, holder/due time, no alarm | | | |
| Lift then scan | LATE_MATCH within grace; otherwise alarm | | | |
| Denied then lift / no session | Immediate shelf alarm + phone evidence | | | |
| Return scan / placement | MATCHED or timed warning if scan/place missing | | | |
| Phone cover/offline/anchors | Health warning/suspended observations; modest pose rectifies | | | |
| WhatsApp actual delivery | Laptop photo for gate, phone photo for shelf; statuses checked | | | |
| Optional Telegram | Independent text + multipart photo delivery | | | |
| 3.3 V supply / runtime RAM | Actual voltage/current/headroom recorded separately | | | |

Historical worksheets follow; current software verification is OPERATIONAL_VERIFICATION.md.

## Historical v2 M2 checkpoint

Use V2_HARDWARE_CHECKPOINT.md and MEASUREMENTS.md first. The original v1 worksheet below is retained as historical/core regression context; replace old REMOVAL tests with reason-coded ALARM SHELF_BREACH. Multi-session, ledger, reconciliation, Telegram and learned/reveal vision tests belong to later milestones, not this checkpoint.

| Test | Expected | Actual | Pass/fail | Raw evidence |
|---|---|---|---|---|
| BOOT/reset/readers | fw 2.0, actual rst, rd and increasing bid | | | |
| Result codes | IN/OUT/ISS/RET success resets; DEN/NSS count; PRM does not | | | |
| PW cancel/deadline | ON/OFF/ESC; one DEADMAN shelf-pattern alarm without PC | | | |
| Button | 30 ms debounce, short mute 30 s, long ACK when enabled | | | |
| WDT hang | Reset on safe bootloader; USE_WDT=0 fallback documented | | | |
| EEPROM vectors/cache | C++ FNV/CRC PASS, WLOK, valid cache retained across reset | | | |
| Offline known badge/item | Local IN/ISS/OUT, level/no-session denials, no PC AUTH | | | |
| Offline unknown x3 | Local gate alarm despite PC/camera/notifier absence | | | |
| Ring/full policy | No overwrite; fail closed with FULL diagnostic | | | |
| Replay | Durable rows before ACK, duplicates do not duplicate | | | |
| Two readers | Correct rd=0/1, stable shared-SPI and supply | | | |
| Actual telemetry | ram/lp/off recorded; no simulation numbers reused | | | |

Software baseline and final command outputs are recorded separately in V2_VERIFICATION.md. New time-based domain tests inject clocks; the complete suite must remain under approximately 90 s on the development laptop.

## 1. Automated software checks

Run from repository root with Python 3.11 venv. Do not connect real hardware to the automated suite; it uses temporary databases and synthetic cameras/serial. `pytest -q` covers protocol rejection, clock-driven firmware behavior, real ArUco image classification, debounce, camera health, API/login/CRUD, CSRF protection, Twilio signatures, retries, signed media, rule attribution, and full threaded scenarios.

```text
python -m pytest -q
npm ci --prefix frontend
npm run build --prefix frontend
npm audit --prefix frontend
python tools/fake_scenarios.py
python tools/protocol_conformance.py --simulate
```

Actual development results are in VERIFICATION.md. These commands do not prove electrical behavior, camera geometry, WhatsApp delivery or real-time latency.

## 2. Hardware readiness

1. Inspect wiring unpowered; verify RC522 3.3 V and protected UNO outputs.
2. Upload reader test and record UIDs, then output test and observe each LED/buzzer.
3. Upload main firmware; stop the dashboard before running `python tools/hw_selftest.py --port COM3`. It requires operator observations and fails unanswered tests.
4. Run `python tools/protocol_conformance.py --port COM3`. Follow card-tap prompts. Success: asserted SESSION, FAIL, ALARM and ALARM_OFF replies. Remove/re-present cards, at least 1.5 s apart.
5. Start the app, finish calibration and sandbox setup, warn nearby people, and run the worksheet below. Never mark a test passed merely because a command was queued.

## 3. Functional worksheet (fill on actual hardware)

| ID | Procedure | Expected result | Actual result | Pass/fail | Evidence / date |
|---|---|---|---|---|---|
| G1 | Tap valid card from OUT | Green steady, named session IN | | | |
| G2 | Tap same card after removing for 1.5 s | Double green blink, session OUT | | | |
| G3 | While A IN, tap valid B | BUSY, A remains IN, no alarm | | | |
| G4 | Unknown card once | Red 2 s, failed scan and gate JPEG | | | |
| G5 | Unknown card 3 times within 60 s | Third failure buzzer/red, critical incident and gate photo | | | |
| G6 | Two failures then valid card | Counter resets, no threshold alarm | | | |
| G7 | Two failures, wait >60 s, fail once | New count 1, no threshold alarm | | | |
| G8 | Close app, tap three unknown cards | TIMEOUT failures and autonomous local alarm | | | |
| G9 | Wait alarm duration / press Acknowledge | Stops at 30 s / immediately by ACK | | | |
| G10 | Stop/restart app while worker IN | Same open DB session restored with SYNC | | | |
| S1 | Remove box while worker IN | Attributed worker event; no buzzer | | | |
| S2 | Remove box while OUT | UNO alarm, incident, T-2/T0/T+1 photos and 6 s clip | | | |
| S3 | Cover marker with hand >2 s, box stays | OCCLUDED warning, no buzzer | | | |
| S4 | Return removed box while OUT | PRESENT and return/tampering warning | | | |
| C1 | Stop phone stream >3 s | OFFLINE warning and dashboard banner | | | |
| C2 | Cover lens >2 s | COVERED warning, no invented removal | | | |
| C3 | Shift phone / hide anchors >3 s | MOVED warning if anchors established | | | |
| C4 | Restore stream/lighting | Automatic reconnect and health recovery | | | |
| F1 | Disconnect gate camera, trigger gate alarm | Buzzer/logging continue; photo unavailable recorded | | | |
| F2 | Disconnect both cameras and internet, fail gate 3 times | Autonomous gate buzzer still works | | | |
| F3 | Stop laptop heartbeats >6 s | Alternating LEDs, no accepted AUTH until HB returns | | | |
| N1 | Owner hello, trigger incident after 20 s quiet | Text + JPEG on phone, callback delivery status | | | |
| N2 | Expired service window / simulated 63016 test | FAILED_SESSION_EXPIRED and reopen-session banner | | | |
| N3 | Tamper media token / use expired token | HTTP 403, no file disclosure | | | |
| N4 | Trigger same incident kind twice <20 s | Second alert rate-limited; both incidents retained | | | |
| R1 | Keep incident; run retention with old files on a backup dataset | Kept evidence/references survive; other expired media removed | | | |
| A1 | Logged out, fetch evidence/API/WS | Access rejected | | | |
| A2 | Enrol next card, then save personnel | UID fills form, scan stays denied until saved | | | |

Record lighting, phone model/app, resolutions, marker size, distance, thresholds, firmware build and ports beside each run. Repeat ambiguous outcomes rather than guessing.

## 4. Measure physical latency

Host JSON timestamps cannot reveal the exact moment an LED illuminates or a buzzer starts. `latency_bench.py` therefore consumes **actual instrument edge times**, not synthetic timings. You need a logic analyzer with enough channels and a shared ground; use the lab's equipment under instructor supervision. Never connect a 3.3 V-only analyzer to a 5 V UNO pin without a rated input/probe/divider.

1. With power disconnected, connect analyzer GND to UNO GND and protected probes to serial TX/RX, D7, D8 and D6. Configure at least 1 MHz sampling and serial decode 115200 8N1. D6 starts pulsing for passive buzzers; measure the first drive edge. This measures electrical actuation, not acoustic propagation. A photodiode/microphone adds real light/sound measurements if the report requires those.
2. For `scan_to_led`, use the end of the decoded SCAN newline as start_us, and first D7 rising edge for authorized check-in or D8 rising for denial as end_us. Label this precisely as **SCAN emission to LED drive**, not card-presentation-to-LED. To measure physical card-presentation time, add an independently timed optical/proximity trigger and document its location.
3. For `third_failure_to_buzzer`, start at the final stop bit of the third denied AUTH packet reaching the UNO and end at first D6 drive edge. For timeout failures, use SCAN end + 1000 ms as the defined failure start, and record that method separately.
4. For `removal_to_buzzer`, start at the final stop bit of REMOVAL reaching the UNO and end at first D6 edge. This isolates UNO response; it excludes camera/debounce delay. To measure end-to-end physical removal, use an independent trigger when the box leaves its slot and note that definition instead.
5. Collect at least 20 trials per metric, ACK/reset between alarms, and ensure the worker is OUT for shelf alarm trials. Export measured edges to a CSV containing `metric,start_us,end_us` (timestamps in microseconds from the **same instrument clock**). Do not fill it with assumed values.
6. Run `python tools/latency_bench.py --measurements your-real-trials.csv`. It prints sample counts, median and nearest-rank 95th percentile in ms. Missing metrics print NOT MEASURED and exit nonzero. Preserve raw traces and definitions with the report.

| Metric | Start definition used | Trials | Median ms | 95th percentile ms | Raw trace location |
|---|---|---|---|---|---|
| scan_to_led | | | | | |
| third_failure_to_buzzer | | | | | |
| removal_to_buzzer | | | | | |

## 5. Acceptance and demo rehearsal

- [ ] Automated suite and frontend build pass on the presentation laptop.
- [ ] Firmware compile and physical output checks pass with recorded versions.
- [ ] All gate and shelf scenarios above have actual results.
- [ ] Gate alarm remains independent of network/camera/DB failures.
- [ ] Marker/ROI calibration stable for at least ten minutes in demo lighting.
- [ ] WhatsApp owner joined and inbound window reopened immediately before demo.
- [ ] Evidence hashes recomputed for at least one downloaded file and compared with DB.
- [ ] Real timing measurements filled with raw trace references.
- [ ] No secrets, private photos or personal phone numbers in slides/source/screenshots.
- [ ] All open alarms acknowledged and expected initial state OUT/PRESENT established.
