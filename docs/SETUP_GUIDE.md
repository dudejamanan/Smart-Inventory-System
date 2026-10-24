# Software setup

## 1. Install runtimes

1. Install **Python 3.11** from [python.org](https://www.python.org/downloads/) (Windows: select the Python launcher and Add Python to PATH). Open a new terminal and run `py -3.11 --version` on Windows or `python3.11 --version` elsewhere. Success: Python 3.11.x. Newer Python versions may not have compatible wheels for the pinned computer-vision packages.
2. Install Node.js 22 LTS or 24 from [nodejs.org](https://nodejs.org/). Run `node --version` and `npm --version`. Success: both print versions. This repository was built using Node 24.
3. Open a terminal at the repository root. On this machine: `cd D:\inventorySystem`. Windows examples below use PowerShell and do not require activation scripts.

## 2. Install and build

Windows:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -r backend/requirements.lock.txt
npm ci --prefix frontend
npm run build --prefix frontend
.\.venv\Scripts\python scripts/init_env.py
```

Linux/macOS:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock.txt
npm ci --prefix frontend
npm run build --prefix frontend
.venv/bin/python scripts/init_env.py
```

The venv is an isolated Python dependency folder. The script asks for an admin password (at least 12 characters) and generates two long signing secrets in .env. It never overwrites an existing .env or prints its secrets. Success: installation completes, Vite prints `built`, and .env exists but `git status` does not show it. Do not share the file or evidence directory. If pip cannot find wheels, verify that the command uses Python 3.11, 64-bit.

## 3. Run simulation first

1. Windows: `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1`. Linux/macOS: `bash scripts/dev.sh`. The bypass applies to this script invocation, not a permanent machine policy change.
2. Open http://127.0.0.1:8000 in the browser. Sign in using the chosen password. Success: shelf shows three synthetic marker boxes; gate shows a synthetic person; System health shows SimulatedArduino/MockNotifier behavior and connected serial after a heartbeat.
3. In Live > Simulation controls, tap Aarav's card. Success: worker name and active session. Tap again after at least 1.5 s to check out. Remove Bay 1 while unattended: alarm, critical incident and evidence appear. Acknowledge it, return the item and review the warning.
4. Run all automated scenarios in another terminal: `.\.venv\Scripts\python tools/fake_scenarios.py` (or `.venv/bin/python ...`). It creates a temporary database and **never sends real WhatsApp messages**, even if your .env contains Twilio credentials. Success: ten PASS lines and final completion text.
5. To run the entry point directly: `cd backend`, then `..\.venv\Scripts\python -m app --simulate`. From root, set `$env:PYTHONPATH='backend'` first (bash: `PYTHONPATH=backend .venv/bin/python -m app --simulate`). Ctrl+C stops the app and releases cameras/serial.

Without .env, simulation permits an empty password for local exploration and ephemeral signing keys; real mode will refuse to start. Configure secrets before making any tunnel public. Simulation uses the real notifier if real credentials are deliberately supplied to normal app startup; leave them blank for a no-cost demo.

## 4. Configure real hardware

1. Stop simulation and finish HARDWARE_GUIDE sections 2–7, including uploads and physical output tests. Close Arduino Serial Monitor and every serial tool.
2. Edit only .env locally. Set SERIAL_PORT (e.g. `COM3` or `/dev/ttyACM0`), GATE_CAMERA_INDEX=0, and SHELF_STREAM_URL from PHONE_CAMERA_SETUP. Keep SERIAL_BAUD=115200. If multiple webcams exist, test indices 0 and 1 with camera_test.py.
3. Simulation and real mode otherwise use the same data folder. **Before a real demonstration**, stop the app and move the simulation data folder to a clearly labeled backup outside the working data path, or set `DATA_DIR` in .env to an empty absolute folder. This prevents fake demo UIDs and synthetic calibration from authorizing real cards. Never delete a real evidence database casually.
4. Start `scripts/dev.ps1 -Hardware` (or `bash scripts/dev.sh --hardware`). With no SERIAL_PORT, auto-detection works only when exactly one recognized USB serial board is present. Prefer an explicit port.
5. Sign in. Success: serial connected, both cameras OK, no synthetic image. Enrol actual personnel, add inventory and slots, print markers and calibrate. Real mode has no automatically authorized cards.
6. Configure Twilio only after gate/vision work; use TWILIO_SETUP. Lack of notifications must not prevent local alarms or evidence.

## 5. Tests and development

```powershell
.\.venv\Scripts\python -m pytest -q
npm run build --prefix frontend
.\.venv\Scripts\python tools/protocol_conformance.py --simulate
.\.venv\Scripts\python tools/print_markers.py --output data/markers.pdf
```

For marker output, create data first if it does not exist (`New-Item -ItemType Directory -Force data`). Success: pytest passes, frontend builds, protocol cases PASS, PDF opens with labeled black marker squares. Hardware-only tests are in TEST_PLAN; simulation is not a substitute.

For UI development, keep the backend on port 8000 and run `npm run dev --prefix frontend` in a second terminal. Visit port 5173; Vite proxies API and WebSocket traffic. Build again before using the backend-served dashboard. Run only one backend worker; do not enable reload while real serial hardware is in use. Never expose the Vite server through a tunnel.

## 6. Configuration and maintenance

`.env.example` lists defaults. The Settings dashboard persists nonsecret options into SQLite; these override .env on next startup. Alarm/detection thresholds apply immediately. Restart after changing serial connections, camera sources or capture rate. Secrets and camera URL credentials remain only in .env (credential-bearing URLs are not displayed or saved in settings). To revert a persisted option, change it through Settings. Config validation rejects invalid debounce ratios. UNO AUTH/watchdog timers are compile-time config.h values and must match the laptop timing policy.

Retention runs at startup and hourly. Default is 30 days; mark important incidents Keep before they expire. Empty calibration references are retained. Logs go to the terminal. Stop the app before backing up data; preserve the database and all evidence/reference folders together. If phone position/lighting changes, recalibrate. Update dependencies deliberately, regenerate lockfiles, rerun tests and build, and record changes in DECISIONS.

## 7. Optional zones

Leave ZONES_ENABLED=false for the core project. To demonstrate zone permissions, enable zones in Settings, add zones under Inventory, note their record IDs, and set each relevant shelf slot's zone_id. Open Personnel > Zone permissions, select a worker, tick their allowed zones and save. Unzoned slots are unrestricted. With an active worker, removing a box in a zone without an assignment creates a WARNING incident and no buzzer; granting the assignment suppresses that warning. Disabling the flag stops permission enforcement while retaining assignments. API equivalents are CRUD `/api/zones` and GET/PUT `/api/personnel/{id}/zones` with `{"zone_ids":[1,2]}`. Remove assignments and unset slot zone IDs before deleting a referenced zone.
