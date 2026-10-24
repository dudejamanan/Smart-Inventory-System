# Verification report

Software verification completed in this workspace on 2026-10-24 (Asia/Calcutta). This report distinguishes actual command outputs from work that needs the student's equipment/accounts. No real electrical timing or WhatsApp delivery numbers were generated.

## Built

UNO firmware and unit sketches; Python/FastAPI/SQLAlchemy backend; real/simulated serial and camera sources; ArUco slot classification and health; gate photos; incidents, hashed shelf evidence, retention; isolated mock/Twilio notification queue and signed webhooks/media; authenticated React console with management, ROI calibration and health; marker/hardware/scenario/latency tools; Windows/bash launch scripts; detailed guides and optional zone permissions. M1–M10 are committed separately by milestone, with follow-up hardening commits.

## Verified commands and observed output

Windows commands below run from `D:\inventorySystem`. Equivalent activated-venv commands are documented in SETUP_GUIDE.

| Command | Actual result |
|---|---|
| `.\.venv\Scripts\python -m pytest -q` | **28 passed, 1 warning in 39.43s** |
| `npm run build --prefix frontend` | TypeScript passed; **Vite v6.4.5 built**, 26 modules; final JS 164.04 kB, gzip 52.47 kB |
| `npm audit --prefix frontend` | **found 0 vulnerabilities** |
| `.\.venv\Scripts\python -m pip check` | **No broken requirements found.** |
| `.\.venv\Scripts\python -m ruff check backend tools scripts --select F` | **All checks passed!** |
| `.\.venv\Scripts\python -m compileall -q backend tools scripts` | Exit 0, no syntax diagnostics |
| `.\.venv\Scripts\python tools/fake_scenarios.py` | Ten PASS scenarios; **All 10 end-to-end scenarios passed. Synthetic hardware; no electrical claims.** |
| `.\.venv\Scripts\python tools/protocol_conformance.py --simulate` | PASS for SYNC, unattended REMOVAL/SHELF_BREACH, ACK, PC_CMD alarm, ACK |
| `.\.venv\Scripts\python tools/print_markers.py --output build/markers.pdf` | **Wrote build/markers.pdf: 40 markers** (items 0–29, anchors 40–49) |
| `git ls-files .env data` | No output: neither secrets file nor runtime/evidence data tracked |

The pytest warning is a Starlette TestClient reference to a deprecated AnyIO BlockingPortal alias. It is not a failed test. Runtime libraries are pinned in requirements.lock.txt; frontend dependencies are pinned in package-lock.json. Ruff 0.11.8 and Prettier 3.5.3 were used as development formatters, not runtime dependencies.

The ten full scenarios exercise valid card, one unknown, three unknown, two wrong then right, authorized removal, unattended removal, hand occlusion, covered camera, serial disconnect, and restart/SYNC with an open session. They use actual threads, HTTP routes, SQLite files, generated marker images, OpenCV detection and evidence encoding. Twilio is mocked. Additional regression tests inject a failed database and hold the rules lock to verify AUTH/REMOVAL dispatch isolation, force codec failure to check JPEG fallback/hashes, and verify Keep/reference retention and zone warning gating.

## Firmware compiles (actual AVR compiler)

Local CLI: `build/arduino-cli/arduino-cli.exe`, reported version **1.5.2-rc.1**. AVR core **arduino:avr 1.8.6**, MFRC522 **1.4.12**, avr-gcc **7.3.0-atmel3.6.1-arduino7**. The normal CLI download initially failed DNS; official archives and package-index SHA-256 validation provided a local ignored toolchain. No board was required for compilation.

```powershell
.\build\arduino-cli\arduino-cli.exe compile --config-file build/arduino-cli.json --fqbn arduino:avr:uno --output-dir build/firmware-active firmware/arduino_gate
.\build\arduino-cli\arduino-cli.exe compile --config-file build/arduino-cli.json --fqbn arduino:avr:uno --build-property 'compiler.cpp.extra_flags=-DBUZZER_ACTIVE=0' --output-dir build/firmware-passive firmware/arduino_gate
```

| Build | Actual flash usage (max 32256) | Actual global RAM (max 2048) |
|---|---|---|
| Main active buzzer | 9176 bytes (28%) | 569 bytes (27%), 1479 remaining for locals |
| Main passive buzzer | 9896 bytes (30%) | 586 bytes (28%), 1462 remaining for locals |
| rfid_test | 4860 bytes (15%) | 215 bytes (10%) |
| led_buzzer_test (active) | 1906 bytes (5%) | 184 bytes (8%) |

For the unit sketches, each .ino was copied into a matching folder under build, then compiled with the same `--config-file ... --fqbn arduino:avr:uno` command. An earlier `--warnings all` run reported unused-parameter warnings in the Arduino core's new.cpp; project compilation succeeded. Flash/RAM percentages do not measure electrical behavior or worst-case stack usage.

## Live application/browser check

The real CLI entry point was launched with `PYTHONPATH=backend`, `DATA_DIR=D:\inventorySystem\build\preview-data`, and `python -m app --simulate --port 8123`. Uvicorn reported **Application startup complete** and **running on http://127.0.0.1:8123**. Port 8000 belonged to an existing process and was left alone.

In the browser, the built dashboard signed in, showed connected simulated serial, healthy synthetic shelf/gate cameras, and all three slots PRESENT. Personnel management rendered the two demo workers and record/form controls. The final simulator remains available at http://127.0.0.1:8123 while its process runs. With no .env configured for this local preview, sign in with an empty password. Create your own .env before exposing any server beyond loopback.

## Not verified (and why)

| Check | Why it still needs a human |
|---|---|
| Actual UNO flash/upload and RC522 card reads | No connected physical board/reader/cards were used |
| LED polarity, voltage levels, buzzer current/type/sound | Requires wiring inspection, a meter and physical observation |
| Real serial reconnection/driver behavior | Simulated serial was tested; no real COM port device available |
| Laptop gate webcam and phone MJPEG | Tests/preview use synthetic images; actual devices and local network URL are user-specific |
| Real shelf layout, exposure and calibration thresholds | Must be calibrated in the physical scene under demo lighting |
| Real Twilio text/photo delivery, callbacks and sandbox/session membership | No user's Twilio account credentials or owner phone were supplied; SDK and signatures tested with mocks |
| Physical latency medians/p95 | No instrument or real timestamp CSV; tools refuse to manufacture measurements |
| Linux/macOS launcher execution | Built/tested on Windows; bash script is supplied but not run on those operating systems |
| Old OpenCV ArUco branch on an old wheel | Compatibility branches supplied; installed/tested OpenCV is 4.11.0 |
| Long-duration load, power cycling and temperature behavior | Requires real hardware and an extended supervised run |

## Assumptions and limits

- One gate, one active worker and one shelf camera, with one backend process. A DB outage after configuration load cannot block outgoing AUTH/REMOVAL, but failed database writes cannot magically preserve history; inspect logs and restore storage. Starting from an unreadable DB cannot reconstruct whitelist/calibration.
- Camera failure cannot reveal unseen shelf motion. It produces a warning; autonomous gate failure alarms remain available. Empty-reference similarity is a calibrated heuristic, not proof that an object is absent.
- Camera movement baseline resets at startup; verify the scene first. Clips pad unavailable pre/post frames with the nearest real frame. Evidence hashes verify file consistency relative to recorded hashes, not a forensic chain of custody.
- RFID UIDs can be cloned. This student prototype does not operate a physical door lock and is not a production authentication system.
- WhatsApp uses free-form sandbox messages only; no approved out-of-session templates. Notification queues are in-memory, so an abrupt kill can leave queued rows pending; normal shutdown cancels remaining work. No automatic replay of ambiguous sends, to avoid duplicate owner messages after restart.
- latency_bench.py summarizes real instrument traces; it does not acquire electrical edges itself. TEST_PLAN explains acquisition, trigger definitions and the distinction from host/software timings.
- Configuration table values override .env for supported nonsecret options. Source/serial/capture-rate changes require restart; UNO timer constants require firmware changes. This version creates a fresh schema and has no migration system for historical development schemas.
- Optional zones are warning-only, disabled by default. No assignment means denied for zoned slots; unzoned slots are unrestricted.

Official API references and individual choices are recorded in DECISIONS.md. DevRelay community/event research was attempted but unavailable because the account is not connected; no community citations or event matches were invented.

## Next steps

Follow the ordered checklist in [HUMAN_TODO.md](HUMAN_TODO.md): configure your local secrets, assemble/check/upload hardware, test real gate and cameras, enrol personnel, print/calibrate markers, configure/join/test WhatsApp, then fill in real functional and latency worksheets and rehearse. All hardware-result fields remain blank in TEST_PLAN.md for your observations.
