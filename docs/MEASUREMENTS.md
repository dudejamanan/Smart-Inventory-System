# Real measurements (blank until you measure them)

Compilation, simulation and host timestamps are not electrical results. Keep raw output/traces, the firmware variant, board model, port, lighting, supply arrangement and date beside each observation. All result cells below are intentionally blank.

## Compile versus runtime memory

`python tools/compile_firmware.py` reports static flash/global RAM. On real hardware, HB ram is a point-in-time stack/heap gap; it is not a proven worst-case stack bound. HB lp is the maximum measured loop duration in microseconds since the previous HB. EEPROM commits can make a loop longer. Do not copy simulator ram=0/lp=0 into a physical results table.

| Variant / board | Actual supply V | Minimum observed HB ram B | Maximum observed lp µs | Reset cause observed | Raw output |
|---|---|---|---|---|---|
| Reader 1 active | | | | | |
| Reader 1 passive | | | | | |
| Reader 2 active | | | | | |
| Reader 2 passive | | | | | |

## Firmware feedback latency

1. Stop the app/Serial Monitor. Flash the intended fw 2.0 variant and connect the real board.
2. Run `python tools/latency_bench.py --port COM3 --trials 20 --output data/feedback.jsonl` with your port. Tap/remove cards as prompted. The tool returns PRM, so red/two-beep feedback occurs without adding gate failures.
3. The tool records real FB and prints median and nearest-rank p95. Name this **SCAN to firmware feedback-drive code**, not optical/acoustic response. FB starts after the GPIO/tone code is invoked; it excludes physical tag-presentation timing and sound travel.
4. Reanalyze saved actual output with `--feedback-log data/feedback.jsonl`. Never feed simulator samples into your physical report.

| Variant / measured path | Samples | Median ms | p95 ms | Actual source/log | Date |
|---|---|---|---|---|---|
| SCAN -> FB drive code | | | | | |
| Third denied AUTH -> buzzer drive | | | | | |
| PW deadline -> buzzer drive | | | | | |
| Shelf ALARM command -> buzzer drive | | | | | |

## Electrical and visible/acoustic latency

Use the trigger definitions and safe probe instructions in TEST_PLAN §4. v2 replaces REMOVAL with `ALARM on=1 why=SHELF_BREACH`; record that command's final stop bit as the electrical start. External CSV remains `metric,start_us,end_us`, with supported metrics scan_to_led, third_failure_to_buzzer and removal_to_buzzer. Run `python tools/latency_bench.py --measurements data/actual-edges.csv`. Keep all times on one instrument clock.

For slow-motion observations, record `metric,frames` in a CSV and use `--slow-motion-frames data/actual-video.csv --fps 240` (replace FPS with the camera's **actual** rate). Start/end frames must come from real visible events. Quantization is at least one frame; auto/interpolated slow motion and audio synchronization can add error. A phone video cannot automatically isolate serial command arrival without a visible synchronized trigger. Do not claim it measures a hidden electrical edge.

## EEPROM / offline / safety observations

| Test | Actual result | Pass/fail | Evidence/output |
|---|---|---|---|
| FNV/CRC shared vectors on real AVR | | | |
| Scratch EEPROM read/write/restore | | | |
| Whitelist WLOK and retention after reset | | | |
| No heartbeats -> pcok=0, known badge still accepted | | | |
| Offline item sufficient / insufficient level | | | |
| Offline badge IN/OUT and pending event count | | | |
| Real OFF replay and duplicate-safe SQL rows | | | |
| Unknown x3 while offline -> local alarm | | | |
| PW deadline with PC silent -> DEADMAN | | | |
| Short button mute / long acknowledge | | | |
| Intentional WDT hang -> reset (safe bootloader) | | | |
| Second reader correctly identifies rd=1 | | | |

Do not intentionally remove power during EEPROM writes without an instructor-approved test plan. Software tests cover corrupted/torn images; they are not permission to risk hardware or erase a real audit trail.
