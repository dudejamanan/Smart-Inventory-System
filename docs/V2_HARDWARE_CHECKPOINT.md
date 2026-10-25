# v2 M2: do these hardware steps in order

This is the requested **stop-after-M2** checkpoint. Protocol/firmware, EEPROM offline authorization and replay are implemented. Multiple online sessions, TTLs, online item enrolment/ledger, strict declared-versus-observed reconciliation, Telegram, reveal/rectified vision and the redesigned dashboard are **not implemented yet** (M3–M8). The existing dashboard is a temporary hardware test interface with its old single-worker/session-lenient policy. Do not demonstrate it as full v2 security.

All commands below are PowerShell at `D:\inventorySystem`; use your own port, not necessarily COM3. No command in development flashed a real board. Physical observations still belong to you.

## 1. Prepare and stop serial owners

1. Back up your .env privately and stop the app with Ctrl+C. Close Arduino Serial Monitor and other serial tools. Only one program can own the board port. A browser tab alone does not stop the backend.
2. Run `git branch --show-current`: expect `v2`. `git tag --list v1.0` should show the preserved v1 baseline. Do not switch versions while a backend process is running.
3. Confirm Python 3.11 and the venv. Install dependencies/build if needed as in SETUP_GUIDE. Run `.\.venv\Scripts\python -m pytest -q` and `npm run build --prefix frontend`. Success: tests pass and build completes. The exact development results are in V2_VERIFICATION.md.
4. If .env does not exist, run `.\.venv\Scripts\python scripts/init_env.py` to choose your password and create signing secrets. Keep credentials only there. Set `BOARD_ID=gate-0`; use a new stable identity if replacing/fully erasing a board while keeping an old replay database.

## 2. Wire the one-reader circuit first

Unplug USB before rewiring. Follow HARDWARE_GUIDE for breadboard/LED/RC522 basics. Keep RC522 VCC at **3.3 V**, never 5 V. All grounds are common.

| Component | UNO connection |
|---|---|
| Reader 0 SDA/SS | D10 via 5 V -> 3.3 V divider/shifter |
| Reader 0 RST | D9 via divider/shifter |
| Shared SCK | D13 via divider/shifter |
| Shared MOSI | D11 via divider/shifter |
| Shared MISO | D12 directly from 3.3 V readers |
| Green / red LED | D7 / D8, each through 220 ohm to LED anode; cathode to GND |
| Buzzer driver | D6 to 1k resistor to NPN base; emitter GND, collector to buzzer negative; buzzer positive to rated USB-derived 5 V |
| Push button | D4 to normally-open button to GND; INPUT_PULLUP is enabled |

The NPN (e.g. lab-checked 2N2222 circuit) prevents a larger buzzer drawing current directly from a GPIO. Check its actual pin order from its datasheet; transistor packages differ. For an inductive magnetic buzzer add a suitable flyback diode across it, cathode toward +5 V. A passive piezo uses BUZZER_ACTIVE=0 and tone(); an active buzzer uses 1. Ask your instructor to check any uncertain driver circuit.

Each divider is `UNO output -> 1k -> reader input node -> 2k -> GND`, giving about 3.33 V from 5 V. The reader input connects at the resistor junction. Do not put a divider in the 3.3 V supply or on MISO. Keep leads short; an SPI-rated level shifter/buffer is preferable for reliable edges.

Button success: released D4 reads high, pressed reads low. Debounce is 30 ms. A short press/release mutes sound only for 30 s; holding >=1.5 s and releasing acknowledges if BTN_ACK_ENABLED=1. Neither action erases incident history. A muted new alarm can still flash red without sound, so wait 30 s before evaluating an audible alarm test.

## 3. Optional second reader (only after reader 0 works)

1. Unplug all power. Reader 1 uses **SS D5 and RST D3**. It shares D13/D11/D12 and GND with reader 0. Set READER_COUNT=2 when compiling. Both SS lines must idle high; do not join the two SS signals.
2. There are **six shifted output signals total**: SCK, MOSI, SS0, RST0, SS1, RST1. The two shared shifted SCK/MOSI nodes feed both readers. MISO is shared and not divided. Fit both SS and RST dividers independently.
3. Do not assume the UNO's 3.3 V pin can power two modules. Two RC522 modules can exceed its typical 50 mA budget. Use a checked, regulated **3.3 V supply rated at least 250 mA**, powered from USB through a suitable regulator/module. Keep its 3.3 V output separate from the UNO 3.3 V pin; connect grounds together. Never parallel regulator outputs or feed a reader directly from USB 5 V. Measure 3.3 V before attaching the readers. Get instructor approval for the power arrangement.
4. Upload/run two_reader_test only after checking power and wiring. Success: tapping each physical reader prints its correct number and the expected UID. Shared-SPI module quality, MISO behavior and wiring capacitance require real testing; compilation cannot prove them.

Reserved only: A1/A2 for future HC-SR04, A4/A5 for future I2C LCD. Leave these unconnected at M2; M9 is not implemented.

## 4. Compile, test sketches, and flash main v2

1. Install AVR core 1.8.6 and MFRC522 1.4.12 as in HARDWARE_GUIDE, or use the already downloaded local CLI/toolchain under build when present. Run `.\.venv\Scripts\python tools/compile_firmware.py`. Success: four main variants meet budgets and all six test sketches compile. It never uploads anything.
2. Test reader, LEDs/buzzer and button first. Arduino IDE requires each .ino in a same-named folder. EEPROM test also needs **protocol_core.h** (from firmware/arduino_gate) and **hash_vectors.h** (from firmware/tests) alongside it. The compile helper already prepares folders under `build/firmware-sketch-tests/`.
3. EEPROM test success: Serial Monitor at 115200 prints FNV shared vectors PASS, CRC shared vector PASS and EEPROM scratch round trip PASS. It uses addresses 900–903 and restores original bytes; it does not replace the whitelist or counter.
4. Use wdt_test only on a watchdog-safe bootloader. It deliberately hangs after 5 s and should reset about 2 s later; record BOOT/reset flags. Some old clone bootloaders can loop before the sketch starts. For an affected main sketch, set USE_WDT=0 and re-upload. If upload is blocked by reset loops, use the board's documented manual-reset upload procedure or have an instructor install a modern Optiboot bootloader with an ISP programmer. Do not guess fuse values. MCUSR can be modified by a bootloader, so verify the reported cause on your board.
5. Select one built variant matching your hardware: reader1-active, reader1-passive, reader2-active, reader2-passive. Example **upload** (replace COM3):

```powershell
.\build\arduino-cli\arduino-cli.exe upload --config-file build/arduino-cli.json --fqbn arduino:avr:uno --port COM3 --input-dir build/firmware-v2/reader1-active
```

6. If local build tools are absent, open the main sketch in IDE, set READER_COUNT/BUZZER_ACTIVE/USE_WDT/BTN_ACK_ENABLED in config.h, compile and upload to the correct UNO port. Success: BOOT reports fw 2.0, correct rd, reset cause and nonzero bid, then HB every 2 s. Close Serial Monitor afterward.

## 5. Real protocol and physical self-test

1. Keep the backend stopped. Run `.\.venv\Scripts\python tools/protocol_conformance.py --port COM3`. It checks result feedback and a dead-man deadline while intentionally sending no heartbeats. Follow the same-card prompts; remove/re-present cards and allow >1.5 s. Success: PASS replies, correct physical patterns, and DEADMAN alarm even after pcok becomes 0. Use ACK or long button press to silence.
2. Run `.\.venv\Scripts\python tools/hw_selftest.py --port COM3 --readers 1` (or 2). Answer y only when you actually see/hear each output. It checks a scan/denial exchange, optional reader 1, short/long button events and actual reported telemetry. Success: every observation and exchange passes. Record the telemetry, not simulated values.
3. Do not unplug USB to test PC loss. The board still needs power. On an UNO, opening a serial port can reset it; a reset clears RAM sessions/logs even though EEPROM survives. For a clean offline/replay test the next tool keeps the same port open and pauses heartbeats.

## 6. Offline item/level and durable replay fixture test

1. Read the UIDs of **two different physical tags**: a test badge and a test item. The script is explicit because it **replaces the board's normal whitelist** with those two disposable test entries (badge L2, item L1). It does not enrol the item into the future online ledger.
2. Run, replacing port and both example UIDs with yours:

```powershell
.\.venv\Scripts\python tools/protocol_conformance.py --port COM3 --offline-fixture --badge-uid A1B2C3D4 --item-uid 00112233 --replay-db-dir data/hardware-replay
```

3. Complete the online/dead-man prompts first. The tool uploads the two-entry cache and waits for WLOK. It then stops heartbeats without closing the port. Success: HB pcok=0 after ~6 s.
4. Follow prompts: tap badge -> IN; tap item -> ISS; tap badge -> OUT. No PC AUTH is sent for those taps. Success: local feedback codes/patterns and offline events pending increase. An unknown badge should still be denied and three failures alarm; test those separately after confirming the legal path.
5. The tool resumes HB, receives OFF and uses the actual backend replay service to commit records before OFFOK. It deliberately processes duplicates and checks one row per identity. Success: PASS durable replay/dedup and a printed database directory. Preserve that output for your report. Do not confuse this fixture with the normal application's database.
6. Restart normal backend mode afterward to replace fixtures with the real active personnel whitelist. **Wait for CURRENT/WLOK before relying on the new offline list.** A failed synchronization leaves the previous committed list intact. A revoked badge is not revoked offline until the new cache commits.

## 7. Run the normal M2 backend

1. Use your private .env with actual SERIAL_PORT and camera settings. Real mode starts with an empty real database unless you deliberately seeded/simulated it; use a clean DATA_DIR for hardware so fake demo badges are not authorized.
2. Start `scripts/dev.ps1 -Hardware`, sign in, enrol/save real badges. In System health verify firmware 2.0, reader count, positive reported RAM, loop-time field, cache count and offline whitelist CURRENT. Allow a few seconds for paced synchronization. M2 sync uses badge level 1; online item tags/real clearance editing arrive at M3.
3. Validate IN/OUT for one worker. A second different active badge currently gets PRM under the temporary PC policy. Multiple offline badges are supported on the board; multiple online DB sessions are M3 work.
4. `/api/offline/events` provides authenticated replay history; System health's event log includes OFFLINE_EVENT after durable replay. Replay at M2 does not reconstruct the future loan ledger or merge offline users into online sessions.
5. Keep cameras optional during gate/offline tests. Shelf vision and alerts retain v1 behavior until M4/M6. Cover/disconnect cameras and the network to confirm local gate/dead-man behavior still works. Do not claim an offline shelf alarm: without the PC camera/rules pipeline, new shelf removals cannot be observed.

## 8. Record measurements and report back at the checkpoint

Use MEASUREMENTS.md for blank tables. Save real tool output, compile variant, UIDs redacted for public sharing, supply voltage, actual reset cause, minimum observed RAM/max loop time, button behavior, offline event counts and replay result. Physical FB samples: `python tools/latency_bench.py --port COM3 --trials 20 --output data/feedback.jsonl`. It sends PRM for each real card scan and computes firmware feedback latency; it is not an optical or acoustic measurement. Instrument/video modes are documented separately.

Stop here for the requested M2 hardware review. Carry your observations into M3–M8 work; do not claim the remaining declared-versus-observed system has shipped.
