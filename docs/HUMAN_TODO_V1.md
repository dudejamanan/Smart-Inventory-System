# Human checklist (do in order)

Everything below needs your equipment, physical observations, local installation choice, or private accounts. Tick only after the success check in the linked section. Software was built/tested in this workspace; installation on another laptop still needs verification.

1. [ ] Read the safety and voltage rules before powering anything: [Hardware §3](HARDWARE_GUIDE.md#3-rc522-voltage-and-level-shifting), [§11](HARDWARE_GUIDE.md#11-safety).
2. [ ] Collect and verify all parts, especially 13.56 MHz cards, 220-ohm LED resistors, 1k/2k dividers, and the buzzer's rated current/type: [Hardware §1](HARDWARE_GUIDE.md#1-parts-and-vocabulary), [§4](HARDWARE_GUIDE.md#4-leds-and-buzzer).
3. [ ] Install Python 3.11, Node 22/24, and project dependencies on the demo laptop; build the dashboard: [Setup §1–2](SETUP_GUIDE.md#1-install-runtimes).
4. [ ] Generate your own .env password and secrets with init_env.py; keep the file private: [Setup §2](SETUP_GUIDE.md#2-install-and-build).
5. [ ] Start simulation, try the Live controls, run pytest and all ten scenarios: [Setup §3](SETUP_GUIDE.md#3-run-simulation-first), [Test §1](TEST_PLAN.md#1-automated-software-checks).
6. [ ] Wire the circuit **with USB unplugged**, including RC522 level protection, common ground, LEDs and suitable buzzer/driver; obtain an instructor/partner check: [Hardware §2–5](HARDWARE_GUIDE.md#2-pin-by-pin-wiring).
7. [ ] Power by USB and verify approximately 3.3 V at RC522 and no heating: [Hardware §5](HARDWARE_GUIDE.md#5-assemble-safely-and-check-power).
8. [ ] Install Arduino IDE/CLI, AVR UNO core and pinned MFRC522 library; select actual port and board: [Hardware §6](HARDWARE_GUIDE.md#6-install-tools-and-upload).
9. [ ] Upload rfid_test, read and record each card's UID; upload led_buzzer_test and observe green/red/sound/silence: [Hardware §6](HARDWARE_GUIDE.md#6-install-tools-and-upload).
10. [ ] Set active/passive flag, upload main sketch, confirm BOOT/HB, close Serial Monitor: [Hardware §6](HARDWARE_GUIDE.md#6-install-tools-and-upload).
11. [ ] Run hw_selftest and real protocol_conformance with app stopped, record observed passes/failures: [Test §2](TEST_PLAN.md#2-hardware-readiness).
12. [ ] Mount gate camera/reader at an appropriate face/tap position and obtain demo-photo consent: [Hardware §8](HARDWARE_GUIDE.md#8-gate-layout).
13. [ ] Install/configure phone streaming app, same-network URL, charger, focus/exposure and mount; test camera_test.py: [Phone §1–3](PHONE_CAMERA_SETUP.md#1-select-and-connect-a-stream).
14. [ ] Use a clean real DATA_DIR so fake demo UIDs/synthetic calibration do not authorize real cards. Set actual serial/camera values and start hardware mode: [Setup §4](SETUP_GUIDE.md#4-configure-real-hardware).
15. [ ] Enrol real personnel; test IN/OUT/BUSY and one/three denied scans: [Hardware §7](HARDWARE_GUIDE.md#7-enrol-cards-and-verify-gate-behavior).
16. [ ] Add inventory/slots, generate marker PDF, print at 100%, measure 4–5 cm squares, attach unique item markers and fixed anchors: [Hardware §9](HARDWARE_GUIDE.md#9-shelf-layout), [Calibration §1](CALIBRATION_GUIDE.md#1-prepare-the-scene).
17. [ ] Draw each ROI, capture empty references with hands/boxes removed, tune/check PRESENT/ABSENT/OCCLUDED: [Calibration §2–5](CALIBRATION_GUIDE.md#2-draw-and-save-each-roi).
18. [ ] Create your Twilio account/testing sandbox, join from owner phone, copy private SID/token into .env: [Twilio §1](TWILIO_SETUP.md#1-account-and-sandbox).
19. [ ] Install/configure an HTTPS tunnel and PUBLIC_BASE_URL; verify public dashboard login and set correct signed webhook URLs: [Twilio §2–3](TWILIO_SETUP.md#2-public-https-access).
20. [ ] Send an inbound WhatsApp hello and verify positive timer; run explicit twilio_test.py and check actual text/photo plus delivery statuses: [Twilio §4](TWILIO_SETUP.md#4-session-and-delivery-test).
21. [ ] Run every real test in the worksheet, including disconnect/covered camera and independent-alarm tests; fill actual results: [Test §3](TEST_PLAN.md#3-functional-worksheet-fill-on-actual-hardware).
22. [ ] Borrow lab logic analyzer/probes if latency measurements are required. Record real traces, export CSV and run latency_bench.py; do not invent timings: [Test §4](TEST_PLAN.md#4-measure-physical-latency).
23. [ ] Check evidence files and recompute a SHA-256 (PowerShell `Get-FileHash -Algorithm SHA256 path`); test Keep/retention only on a backed-up dataset: [Test §3](TEST_PLAN.md#3-functional-worksheet-fill-on-actual-hardware), [Setup §6](SETUP_GUIDE.md#6-configuration-and-maintenance).
24. [ ] Rehearse in final lighting, reopen owner service window/rejoin sandbox if necessary, check initial OUT/PRESENT/OK state, acknowledge alarms, and preserve measured results: [Test §5](TEST_PLAN.md#5-acceptance-and-demo-rehearsal).
25. [ ] Write your report with real photos/results using [REPORT_NOTES](REPORT_NOTES.md); remove credentials and private faces/phone numbers from shared material, then stop the tunnel and back up data after the demo.
