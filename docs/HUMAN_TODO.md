# Your ordered checklist: v2 M2 hardware checkpoint

The useful v2 prompt is being followed **through M2**, where it explicitly requires a stop for your physical tests. Read [V2_HARDWARE_CHECKPOINT.md](V2_HARDWARE_CHECKPOINT.md) as the primary guide. The original v1 checklist is preserved in HUMAN_TODO_V1.md. Nothing here claims that an actual board was flashed or that physical tests passed.

## While Codex works / preparation

1. [ ] Collect the v1 components plus one normally-open push button for D4, a checked buzzer transistor stage, and optional second RC522. Read safety/3.3 V rules in HARDWARE_GUIDE and checkpoint §2.
2. [ ] Install Python 3.11, Node 22/24, Arduino IDE/CLI and the UNO USB driver if needed. Select AVR core 1.8.6 and MFRC522 1.4.12 (SETUP_GUIDE and checkpoint §1/§4).
3. [ ] Back up real .env/data privately. Generate your own secrets with init_env.py if missing. Do not share tokens, real photos or phone numbers. Do not reset/erase an evidence database to fix a software problem (checkpoint §1).
4. [ ] With USB unplugged, wire reader 0, LED resistors, buzzer driver and D4 button. Have a lab partner/instructor compare every pin and divider against checkpoint §2.
5. [ ] Measure RC522 supply at approximately 3.3 V; inspect common ground and LED polarity. Stop/unplug if hot components or unstable USB appear (HARDWARE_GUIDE §5).
6. [ ] Label two different compatible physical tags for the offline fixture test. Read their actual uppercase UIDs with rfid_test; the example UIDs in commands are not promises about your cards (checkpoint §4/§6).
7. [ ] If using two readers, plan the separate regulated 3.3 V power budget and six shifted output signals with your instructor. Do not power two modules blindly from the UNO 3.3 V pin (checkpoint §3).
8. [ ] Mount the phone and check a direct local stream if desired. Campus Wi-Fi may isolate devices; use a private phone hotspot as described in PHONE_CAMERA_SETUP. New reveal/learn-shelf calibration is not ready until M6.

## After software completion: execute these in order

9. [ ] Confirm branch v2 and preserved tag v1.0. Stop the backend and close every serial monitor/tool (checkpoint §1).
10. [ ] Run pytest, frontend build and `python tools/compile_firmware.py`; record actual output. The compile helper checks four variants and six unit sketches but never uploads (checkpoint §4).
11. [ ] Upload/run reader, LED/buzzer, button and EEPROM/hash sketches. Copy the two required headers for eeprom_test. Record observed PASS text and physical output behavior (checkpoint §4).
12. [ ] Check watchdog-safe bootloader first; run wdt_test only under the guide's instructions. If reset loops occur, recover with USE_WDT=0 or instructor-assisted bootloader repair. Record actual reset behavior (checkpoint §4).
13. [ ] Choose one-reader/two-reader and active/passive settings, then **upload main fw 2.0** to your actual COM port. Confirm BOOT fw/rd/bid and HB, then close monitor (checkpoint §4).
14. [ ] Run real protocol_conformance with the backend stopped. Confirm the physical result patterns and local DEADMAN escalation while heartbeats stop; acknowledge afterward (checkpoint §5).
15. [ ] Run hw_selftest with matching --readers. Observe each light/sound, both button actions, actual telemetry and optional second reader. Do not type y for an unobserved result (checkpoint §5).
16. [ ] Explicitly run the two-tag offline fixture with your real UIDs. It overwrites the cache. Keep USB/serial open while heartbeats pause; verify badge IN, item ISS, badge OUT and durable duplicate-safe replay into data/hardware-replay (checkpoint §6).
17. [ ] Start normal backend hardware mode with a clean real DATA_DIR. Enrol/save real badges, wait for offline cache CURRENT, verify count and firmware telemetry, and restore the normal cache after fixture use (checkpoint §7).
18. [ ] Test unknown card once/three times and camera/notifier outages. Confirm local alarm behavior physically; remember that button mute suppresses sound for 30 s and that no new shelf detection exists while the PC is absent (checkpoint §5/§7).
19. [ ] Collect actual FB/video/instrument samples and fill MEASUREMENTS.md plus TEST_PLAN's M2 worksheet. Keep raw traces/output under data or in a private report folder (checkpoint §8).
20. [ ] **Stop at M2 and provide the hardware results**: board/bootloader, variant, voltages, reader IDs, button results, reset cause, RAM/loop telemetry, offline fixture/replay outcome and any failure output. That is the intended checkpoint before M3–M8.

## Later, after M3–M8 are implemented

- [ ] Enrol real item tags/clearance levels; validate multiple TTL sessions and ledger/CSV.
- [ ] Test matched/late/unissued/denied removal and return reconciliation before claiming strict security.
- [ ] Configure Telegram privately when its notifier ships; keep WhatsApp optional and test real delivery.
- [ ] Print reveal/anchor marker sheets and run the guided learned-shelf calibration when M6 ships.
- [ ] Follow the eventual full v2 demo script and complete end-to-end acceptance. The requested 18+ v2 scenarios are not all implemented at M2.
