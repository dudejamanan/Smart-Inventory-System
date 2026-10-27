# COM11 integration check — 2026-10-27

The connected circuit was tested physically for the first time in this follow-up. Earlier simulation reports remain historical.

| Check | Actual result |
|---|---|
| USB / main firmware | CH340, COM11; initially 2.1, updated to 2.2; two readers |
| LEDs / buzzer | User confirmed both LEDs and buzzer during output tests |
| Initial reader failure | Reader #1 scanned; #2 did not while both RF fields were active |
| SPI version registers | Stable 0xB2 from both reader addresses |
| Independent chip selects | Scratch register readback 0x12 / 0x25 as expected; original values restored |
| Reader #2 isolated | Repeated real card reads with antenna #1 disabled |
| Updated main firmware | 2.2 uploaded; both rd=0 and rd=1 produced SCAN/FB |
| Real backend integration | Both physical readers produced persisted SCAN and FB events through the running hardware application; sampled FB=11 ms each |
| Reported telemetry | Free RAM 925 B; sampled max-loop field 25440 microseconds; pending offline events 0 |
| Laptop camera | Actual 640x480 capture; live backend health OK |
| Server | http://127.0.0.1:8000, simulate=false, COM11 connected, malformed=0, no firmware error |
| Whitelist | CURRENT, count 0 in fresh hardware DB; pending replay 0 |

The observed failure is consistent with interaction between active readers: disabling reader #1's field enabled #2. Electrical testing is still needed to distinguish RF coupling from supply loading. Firmware 2.2 activates only one field at a time, waits 8 ms without blocking the loop, and adds a 600 ms absence guard to the existing 1.5 s repeat interval. The continuous-presence guard has injected-clock tests; uncontrolled user taps are not treated as a measured long-hold acceptance test.

The temporary diagnostic did not write EEPROM and was replaced by main firmware 2.2. The real backend is left running. Do not open COM11 concurrently in Serial Monitor or another tool. Windows venv launcher/child processes form one backend server, not two independently started services.

## Not yet verified

- Phone camera is OFFLINE: SHELF_STREAM_URL is empty. Configure its real stream and calibrate shelves first.
- WhatsApp is MockNotifier: credentials are absent. No real provider message was sent.
- No people/items/slots are authorised in the fresh data/hardware database. Existing demo data was preserved; PRM/enrolment feedback did not grant a test tag access.
- Real item issue/return/shelf rules, offline replay, watchdog/reset, power/current and optical/acoustic latency need their separate acceptance steps.

Private gitignored logs/images are in data/hardware-check/: initial serial log, register diagnostics, main 2.2 scans, backend status, live backend scan/feedback report, actual laptop image and server logs. No UID/credential/database/image is committed here. FB is firmware drive-start latency, not optical or acoustic latency.

## Regression verification

69 tests passed in 51.16 s (one dependency deprecation warning). All 10 threaded legacy, 4 offline checkpoint and 17 operational checks passed. Locked frontend installation/build passed. All six unit sketches compile.

| Variant | Flash bytes | Global RAM bytes |
|---|---:|---:|
| reader1-active | 15838 | 1006 |
| reader1-passive | 16612 | 1023 |
| reader2-active | 15968 | 1035 |
| reader2-passive | 16742 | 1052 |

All meet flash <24 KiB and global RAM <=1100 B. Dedicated per-variant build paths bypassed a Windows shared Arduino cache cleanup error. Follow CURRENT_SETUP.md for remaining enrolment, phone and Twilio steps.
