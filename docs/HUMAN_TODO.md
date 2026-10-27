# Your remaining steps, in order

Voice follow-up (2026-10-28): local pyttsx3 test was completed and the user confirmed hearing it. See VOICE_ANNOUNCEMENTS.md for mute/rate/volume and the Test voice button. A voice announcement does not replace the independent UNO buzzer or prove a physical access/removal event occurred.

Current guide: [CURRENT_SETUP.md](CURRENT_SETUP.md). The user resumed software development beyond M2 on 2026-10-27. Earlier M2 handoff and verification files are historical. Software checks do not establish any physical result.

COM11 follow-up completed: main firmware 2.2 uploaded, both reader scan/feedback paths and laptop camera checked on real hardware; user confirmed LEDs/buzzer. See HARDWARE_CHECK_COM11.md. Remaining work starts with real badge/item enrolment, phone stream/calibration and provider configuration. Use firmware 2.2 builds below; the 2.1 references describe the minimum supported pin profile.

1. [ ] Back up .env and DATA_DIR privately with the backend stopped. Preserve tag v1.0. Use a separate real hardware data directory; do not authorise fake simulation badges in a real demonstration.
2. [ ] Verify actual circuit: reader #1 SS D10 / RST D9, reader #2 SS D4 / RST D5, shared D13/D11/D12, common ground, 3.3 V readers, appropriate level shifting and sufficient regulated power. Check LED resistors and buzzer current/driver. There is no wired button; firmware disables it.
3. [ ] Activate Python 3.11 venv, install backend lockfile, `npm ci --prefix frontend`, `npm run build --prefix frontend`. Generate missing secrets with scripts/init_env.py. Never share secrets.
4. [ ] Stop serial owners. Run tools/compile_firmware.py. Upload the **current firmware 2.1** reader2-active or reader2-passive build to the actual COM port using the command in CURRENT_SETUP.md. Arduino IDE is optional. Verify BOOT fw 2.1 and rd 2.
5. [ ] Run tools/hw_selftest.py --port COMx --readers 2 and tools/protocol_conformance.py --port COMx. Observe each real LED/buzzer/card response. Skip the absent button. Record actual watchdog/reset/RAM/timing results; no physical results are filled in automatically.
6. [ ] On the phone install/start a local MJPEG streaming app. Put phone/laptop on one trusted Wi-Fi or phone hotspot, verify its actual /video endpoint on the laptop, then run tools/camera_test.py for both cameras. Keep the phone powered, ventilated and awake.
7. [ ] Edit .env: actual SERIAL_PORT, DATA_DIR, GATE_CAMERA_INDEX, SHELF_STREAM_URL, REMOVAL_POLICY=strict_issue, GATE_PHOTO_POLICY=third_failure. Start scripts/dev.ps1 -Hardware; open the built dashboard at http://127.0.0.1:8000.
8. [ ] Enrol real badges with levels and separate item tags with minimum levels/loan duration. Create linked shelf slots. Wait for cache CURRENT; verify badge and item counts. A tag cannot be both a badge and an item.
9. [ ] Print item/reveal/anchor markers. Pause shelf rules in Calibration, put all items present, learn four anchors/rest positions, refine slot ROIs, remove each item to verify reveal/capture empty reference, restore all items and resume. Check all slots PRESENT before alarm tests.
10. [ ] Follow DEMO_SCRIPT.md: legal issue/removal, return/place, denied removal, late match, grace expiry with somebody inside, unattended removal, three wrong gate badges and exactly one saved laptop photo. Cover/disconnect/move phone and verify health warnings rather than invented theft observations.
11. [ ] Set up your Twilio Sandbox/account, join from the owner phone, HTTPS backend tunnel, exact PUBLIC_BASE_URL and signed inbound/status webhooks. Send hello after configuring the inbound URL; verify the 24-hour timer. Run the explicit twilio_test.py command and check actual text/photo receipt. Stop the tunnel when finished.
12. [ ] Optional: configure Telegram independently using TELEGRAM_SETUP.md and run its explicit test. No real notification was sent during software development.
13. [ ] Use the disposable two-tag offline fixture if testing PC loss. Keep the USB port open and pause heartbeats; unplugging USB or reopening UNO serial can reset volatile sessions/logs. Restore the normal whitelist afterward and review offline events manually; they cannot reconstruct an attributed online loan ledger.
14. [ ] Fill only real results in TEST_PLAN.md and MEASUREMENTS.md, attach actual local logs/photos/video privately, and note any remaining hardware/provider failures. Do not replace blank physical measurements with simulated values.

No optional person detector, face recognition, gate barrier, direction sensor, LCD or ultrasonic sensor is included in this circuit. Barcode/RFID declarations and a camera's view cannot prove who physically crossed a door.
