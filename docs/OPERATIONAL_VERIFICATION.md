# Operational build verification

Implementation date: 2026-10-27, branch v2. User-authorised continuation beyond M2; actual reader #2 wiring is SS D4 / RST D5. Firmware 2.1 uses protocol 2.0 and distinguishes this circuit from the old M2 2.0 build. The v1.0 tag is preserved.

Baseline before editing: 49 tests passed, 1 dependency deprecation warning, 44.61 s.

## Verified commands

| Command | Result |
|---|---|
| Python 3.11 venv `python -m pytest -q` | 67 passed, 1 Starlette/AnyIO deprecation warning, 50.44 s |
| `python tools/fake_scenarios.py` | All 10 threaded legacy, 4 M2 offline and 17 operational checks passed; intentional notifier-outage traceback is expected |
| `npm ci --prefix frontend` | Locked install passed; audit reported 0 vulnerabilities |
| `npm run build --prefix frontend` | TypeScript/Vite production build passed |
| `python tools/compile_firmware.py` | Four main variants meet budgets; six sketches compile; nothing flashed |
| `python -m ruff check backend tools scripts --select F` | Passed |
| `python -m pip check` | No broken requirements |
| `git diff --check` | Passed |
| `scripts/dev.ps1 -Port 8124` with isolated ignored data and notifications disabled | Startup passed; built page/authentication/current firmware/two synthetic cameras/cache CURRENT/CSV checked over HTTP |

Browser smoke: signed into the built simulator, entered Aarav, issued the resistor item on reader #2, marked its slot absent and verified ISSUED holder/due time, ISSUE history and MATCHED reconciliation without an incident. Names/dates and physical reader #2 are rendered rather than raw IDs/timestamps. Temporary browser tab and backend were stopped after checking. These are synthetic workflow observations, not physical camera/RFID tests.

Arduino AVR core 1.8.6 / MFRC522 1.4.12 compiler sizes:

| Main variant | Flash bytes | Global RAM bytes |
|---|---:|---:|
| reader1-active | 15604 | 997 |
| reader1-passive | 16378 | 1014 |
| reader2-active | 15708 | 1022 |
| reader2-passive | 16482 | 1039 |

All are below 24 KiB flash and at most 1100 B globals. Unwired button code is disabled; the optional standalone A0 button sketch still compiles. Stack headroom remains a physical measurement.

## Scope

Implemented multiple expiring sessions, badge/item registry and levels, issue/return/denial transactions and CSV, strict removal reconciliation with independently ticking grace deadlines, return/overdue warnings, gate-only failure counting and third-failure saved laptop photos, learned four-anchor alignment/three-anchor affine fallback, reveal/empty-reference shelf observations, calibration pause, ledger/diagnostic UI, WhatsApp configuration diagnostics and independent optional Telegram multipart notifications.

The prior single-session lenient engine is retained as explicit legacy_engine and selected only with REMOVAL_POLICY=session_lenient, for old regression scenarios. It is not the default security policy. New domain timer tests use injected clocks.

## Physical boundary

No real upload, wiring/current/voltage measurement, RFID read, buzzer/button/watchdog execution, camera stream, real calibration or WhatsApp/Telegram delivery was performed. Compiler sizes are not minimum runtime RAM measurements. Pending offline activity is not reconstructed as an attributed online loan ledger. Optional person detection, direction sensing, LCD/ultrasonic and face recognition are absent. See CURRENT_SETUP.md and HUMAN_TODO.md.
