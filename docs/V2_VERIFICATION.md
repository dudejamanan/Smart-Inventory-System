# v2 M2 verification — 2026-10-25

Historical report. Current operational results are in OPERATIONAL_VERIFICATION.md and setup is in CURRENT_SETUP.md.

Branch: `v2`; v1 baseline retained as tag `v1.0`. This completes M0–M2 of CODEX_PROMPT_v2 and stops at its required physical hardware checkpoint. M3–M8 are not complete. See V2_CHANGES.md for the integration boundary and V2_HARDWARE_CHECKPOINT.md for the ordered handoff.

## Automated results

Executed at the repository root on Windows with Python 3.11 in `.venv` and Node 24:

| Command | Result |
|---|---|
| `.\.venv\Scripts\python -m pytest -q` | 49 passed, 1 dependency deprecation warning, 46.82 s |
| `npm ci --prefix frontend` | Installed locked dependencies; audit reported 0 vulnerabilities |
| `npm run build --prefix frontend` | TypeScript and Vite production build passed |
| `.\.venv\Scripts\python tools/fake_scenarios.py` | All ten threaded integration scenarios and four M2 checkpoint scenarios passed |
| `.\.venv\Scripts\python -m ruff check backend tools scripts --select F` | Passed |
| `.\.venv\Scripts\python -m pip check` | No broken requirements |
| `git diff --check` | Passed |
| `.\.venv\Scripts\python tools/compile_firmware.py` | Four main variants within budgets; all six test sketches compile |

The Python suite includes legacy regression coverage, strict v2 framing, feedback/failure rules, deadline behavior, offline permissions and capacity, cache validation, replay transaction/deduplication, synchronization, persisted simulated EEPROM and revocation of remembered offline badges.

One warning comes from Starlette's TestClient importing a deprecated AnyIO alias. Tests pass with the pinned dependency set.

## UNO compiler sizes

AVR core 1.8.6, MFRC522 1.4.12, UNO target. The helper enforces flash below 24 KiB and global RAM at most 1100 bytes.

| Variant | Flash bytes | Global RAM bytes |
|---|---:|---:|
| One reader, active buzzer | 15946 | 1010 |
| One reader, passive buzzer | 16720 | 1027 |
| Two readers, active buzzer | 16008 | 1035 |
| Two readers, passive buzzer | 16782 | 1052 |

Compiled test sketches: button_test, eeprom_test, led_buzzer_test, rfid_test, two_reader_test and wdt_test. These are compilation results, not executed physical tests. Runtime stack headroom and minimum free RAM require the physical telemetry worksheet.

## Physical checks still required

No real board was flashed or exercised during this implementation. No real electrical, RFID, button, watchdog, EEPROM power-interruption, camera, notification or optical/acoustic latency result is claimed. MEASUREMENTS.md and TEST_PLAN.md retain blank physical result fields.

Use V2_HARDWARE_CHECKPOINT.md in order: prepare the environment, wire one reader and button, compile/upload matching firmware, run protocol/self-test, run the disposable offline fixture/replay test, restore the normal cache, then record actual measurements. Only add the optional second reader after the first works.

The normal M2 application still uses the old single online worker/session policy and active badges at offline level 1. The real item ledger, multi-session TTLs, strict reconciliation, Telegram, revised vision and redesigned UI remain later milestones.
