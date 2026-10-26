# Smart Warehouse Access & Inventory Security System

**Current: operational two-reader build, resumed by the user on 2026-10-27.** Reader #1 badges use D10/D9; reader #2 item tags use D4/D5; no button is wired. Includes multiple expiring sessions, item permissions/issue/return ledger, strict shelf reconciliation, phone reveal/anchor calibration, third-failure laptop photos, WhatsApp and optional Telegram. Start with [the complete current setup and logic guide](docs/CURRENT_SETUP.md) and [human checklist](docs/HUMAN_TODO.md). The old M2 checkpoint and verification reports are historical; tag `v1.0` remains preserved. Optional person counting/LCD/ultrasonic are not implemented.

Compile every v2 variant/test sketch with `python tools/compile_firmware.py`. `python tools/fake_scenarios.py` runs ten threaded legacy regressions, four offline checkpoint scenarios and the operational rules/vision table; new domain timers use injected clocks. Main firmware requires v2 protocol; do not pair it with the v1 backend. EEPROM authorization survives reset; offline RAM logs/sessions do not, including UNO resets caused by opening serial.

An Embedded Systems Design course project: UNO/RC522 gate access, phone-camera ArUco shelf monitoring, local alarms, evidence and WhatsApp alerts, with an authenticated React dashboard. Simulation runs the same Python engine, detector, API and frontend without hardware.

Start with [SETUP_GUIDE](docs/SETUP_GUIDE.md). All manual work is ordered in [HUMAN_TODO](docs/HUMAN_TODO.md). Wiring is in [HARDWARE_GUIDE](docs/HARDWARE_GUIDE.md); do not power RC522 at 5 V.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -r backend/requirements.lock.txt
npm ci --prefix frontend
npm run build --prefix frontend
.\.venv\Scripts\python scripts/init_env.py
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
```

Open [the local dashboard](http://127.0.0.1:8000) and enter your chosen password. Simulation seeds Aarav (`A1B2C3D4`), Meera (`11223344`), three inventory items and calibrated synthetic slots. Use the simulation controls on Live. Without .env, simulation alone permits an empty password on localhost; real mode refuses missing/short secrets.

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python tools/fake_scenarios.py
.\.venv\Scripts\python tools/protocol_conformance.py --simulate
```

On Linux/macOS use `python3.11`, `.venv/bin/python`, and `bash scripts/dev.sh`. Real hardware mode: `scripts/dev.ps1 -Hardware` or `bash scripts/dev.sh --hardware`. Always stop the app before opening Arduino Serial Monitor or hardware tools.

The standalone `python -m app --simulate` entry point is run from `backend/` (or set PYTHONPATH=backend). Do not use multiple Uvicorn workers. Use the backend's built dashboard when exposing an HTTPS tunnel; never tunnel the Vite development server.

See [ARCHITECTURE](docs/ARCHITECTURE.md), [PROTOCOL](docs/PROTOCOL.md), [SCHEMA](docs/SCHEMA.md), [TEST_PLAN](docs/TEST_PLAN.md), [DECISIONS](docs/DECISIONS.md), and [verification report](docs/VERIFICATION.md) for design, limitations and actual verification results.
