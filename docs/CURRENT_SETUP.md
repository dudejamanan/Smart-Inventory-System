# Start here: your wired two-reader system

Updated 2026-10-27. This supersedes the old M2 stop instructions for normal operation. The user explicitly requested the remaining operational rules and the following actual pin map. Tag v1.0 remains preserved. No physical board was flashed during development. The current main firmware identifies itself as **2.1** while retaining protocol 2.0; strict mode refuses old 2.0 firmware because its wiring/failure policy differs.

## 1. What each device does

| Device | Role |
|---|---|
| RC522 #1, SS D10 / RST D9 | Person badge: enter; tap the same badge again to leave |
| RC522 #2, SS D4 / RST D5 | Item tag: permitted available item -> ISSUE; issued/missing item -> RETURN |
| Laptop webcam, index 0 | Gate preview in RAM; save an incident photo only at the third rejected badge attempt by default |
| Phone camera, local MJPEG stream | Continuously observe shelf markers, detect position changes, buffer evidence in RAM; save/send evidence for incidents |
| UNO, buzzer D6, green D7, red D8 | Immediate feedback, three-failure alarm, independent grace deadline, offline badge cache |

Both readers share SCK D13, MOSI D11, MISO D12 and ground. D4 is **not a button** in your circuit. BUTTON_ENABLED defaults to 0; an optional future button would use A0. Main firmware defaults to two readers. Software reader numbers are 0 and 1 (physical labels #1 and #2).

Before powering, check these actual electrical details with your instructor: RC522 VCC is 3.3 V; the six UNO-to-reader output signals need suitable level shifting (SCK, MOSI, SS0, RST0, SS1, RST1). MISO connects back directly. The UNO 3.3 V pin is rated only 50 mA: verify the combined module current or use a separate regulated 3.3 V supply with common ground. Never parallel its output with the UNO 3.3 V output. Each LED needs its own resistor. Drive a buzzer directly only when its verified current/voltage is within the GPIO rating; otherwise use the documented transistor driver. Software cannot fix an overloaded supply or a 5 V logic input.

References: [official UNO pinout/current limits](https://content.arduino.cc/assets/Pinout-UNOrev3_latest.pdf), [MFRC522 datasheet](https://www.nxp.com/docs/en/data-sheet/MFRC522.pdf).

## 2. The logical rules

1. Enrol each person's badge with a level 1–3. Each item needs its **own different RFID tag**, item marker 0–19, minimum level and loan duration. One UID cannot be both a badge and an item. If you only own two RFID cards, you can demonstrate one worker and one item; two readers alone do not identify every object.
2. A known active badge on reader #1 opens a session (maximum four). Tapping it again closes that session. Sessions expire after 30 minutes by default. Successful item scans renew that worker's expiry. Only unexpired active personnel sessions restore after restart.
3. An item scan on reader #2 belongs to the most recent badge scan within 30 seconds; after that, attribution is allowed only if exactly one session remains. With several possible workers, the system refuses attribution. Wait for the green feedback on the intended badge before tapping the item. To change the most recent worker already inside, check that worker out and back in; a badge tap is not a separate "select worker" action.
4. A permitted available item becomes ISSUED to that worker and gets a due time. Insufficient level or enabled zone permission gives PRM (red feedback). No attributed session gives NSS. A tag on the wrong reader gives rejection/permission feedback. Item-reader denials do not count toward the gate alarm. Returns may be made by a different logged-in worker and are recorded as RETURN_OTHER.
5. A known item ISSUE authorizes **one** removal of its linked shelf slot within 30 seconds. The phone observes the item marker leaving and a reveal marker or matching empty reference appearing. The stored verdict is MATCHED. A valid issue arriving within ten seconds after a removal gives LATE_MATCH and cancels that slot's grace warning.
6. Removing after a recent denied item scan, or removing with nobody checked in, immediately sends the shelf alarm. An undeclared removal with somebody inside starts PW (red warning/chirp); after ten seconds the alarm sounds. Several pending removals keep the earliest unresolved deadline. Returning the box without scanning does not erase the removal event. The UNO can finish an armed grace timer if the laptop stops responding.
7. Placing an issued item back without RETURN produces RETURN_UNSCANNED after 20 seconds. A RETURN while its slot remains empty expects placement within 60 seconds; otherwise RETURN_NOT_OBSERVED warns. Overdue loans create one warning per issue, independent of the buzzer.
8. The first and second rejected **gate badge** attempts are logged without saving a gate photo. The third rejection within 60 seconds triggers the UNO alarm (30 seconds by default), schedules the laptop photo, and queues WhatsApp text/photo. A successful scan resets the counter. Lift/re-present the card and allow at least 1.5 seconds between attempts.
9. Camera occlusion is not proof of theft. A hand over a marker becomes OCCLUDED; an offline, covered or unaligned phone produces a health warning and suspends new visual decisions. RFID/ledger work continues. No camera can detect a removal while it cannot see the shelf. Learned anchors handle modest camera movement; too few/rejected anchors require fixing the view.
10. Notifications run after controller commands and durable incident logging. Internet/Twilio failure does not prevent a local alarm. Successful queueing is not proof of WhatsApp delivery; inspect notification status and the receiving phone.

The phone does **not** read RFID, run facial recognition or decide who a stranger is. It observes labelled shelf slots. A marker peeled off and left on the shelf can defeat marker-only observation; use fixed reveal markers, empty references, a stable view and supervised testing. This is a lab prototype, not a certified access-control system.

## 3. Install and upload (PowerShell)

Run from `D:\inventorySystem`. Close all existing backends and Arduino Serial Monitor before serial tests. One backend owns both cameras and the UNO.

```powershell
cd D:\inventorySystem
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.lock.txt
npm ci --prefix frontend
npm run build --prefix frontend
python scripts/init_env.py
python tools/compile_firmware.py
```

Run init_env only if .env does not already contain your secrets; back it up privately. Never paste .env or tokens into chat. Existing databases are upgraded additively at startup; back up the entire DATA_DIR with the backend stopped first. Use a separate clean DATA_DIR for real hardware rather than the seeded simulation directory.

Arduino IDE is optional. The ignored local CLI/toolchain is already available on this development machine. The compile helper builds four main variants and all six test sketches; it does not upload. Replace COM3 with the actual Arduino port shown in Windows Device Manager:

```powershell
.\build\arduino-cli\arduino-cli.exe board list --config-file build/arduino-cli.json
.\build\arduino-cli\arduino-cli.exe upload --config-file build/arduino-cli.json --fqbn arduino:avr:uno --port COM3 --input-dir build/firmware-v2/reader2-active
```

Use reader2-passive for a passive piezo. The current build is for D4/D5 on reader #2; do not upload an old M2 binary. If the local CLI is unavailable, Arduino IDE can upload firmware/arduino_gate with AVR core 1.8.6 and MFRC522 1.4.12. Select Arduino UNO and its correct port. Watchdog default is enabled; old clone bootloaders may require USE_WDT=0 and a fresh compile as explained in V2_HARDWARE_CHECKPOINT.md. No fuse changes are part of this procedure.

Run while the backend remains stopped:

```powershell
python tools/hw_selftest.py --port COM3 --readers 2
python tools/protocol_conformance.py --port COM3
```

Tap the initial denial test on reader #1. Button test is skipped because your circuit has no button. Physically observe lights/sound; do not answer yes based only on a serial reply. Record results in TEST_PLAN.md.

## 4. Connect the phone

1. On Android, install **IP Webcam by Pavel Khlebovich** from [Google Play](https://play.google.com/store/apps/details?id=com.pas.webcam). An iPhone can use a streaming app that supplies a direct MJPEG URL; the exact app menus differ. This project does not require a phone browser camera permission page or USB cable.
2. Put phone and laptop on the same private Wi-Fi. If campus Wi-Fi isolates clients, enable a private phone hotspot and connect the laptop to it. Keep mobile data enabled if that hotspot also supplies internet for WhatsApp. Camera streaming itself is local and does not need internet.
3. Grant the app camera permission. Select its rear camera, landscape, about 1280×720 and 10–15 FPS. Start its server (IP Webcam: **Start server**). Keep it running, charged, ventilated and awake; disable battery optimization for that app.
4. Copy the IP address **shown by the app**, for example http://192.168.1.25:8080. In the laptop browser open that address. For IP Webcam, test the direct video endpoint `http://192.168.1.25:8080/video`. The endpoint must return current video, not an HTML settings page. A hotspot address may differ; never copy the example IP blindly.
5. With the backend stopped, test both cameras:

```powershell
python tools/camera_test.py 0 --output data/gate-check.jpg
python tools/camera_test.py http://192.168.1.25:8080/video --output data/phone-check.jpg
```

6. Edit .env privately with your actual values:

```dotenv
DATA_DIR=data/hardware
SERIAL_PORT=COM3
GATE_CAMERA_INDEX=0
SHELF_STREAM_URL=http://192.168.1.25:8080/video
REMOVAL_POLICY=strict_issue
GATE_PHOTO_POLICY=third_failure
LOG_VALID_SCAN_PHOTOS=false
NOTIFY_CHANNELS=whatsapp
```

7. Mount the phone so every item and all four corner anchors are visible. The phone URL stays local; **do not tunnel the phone's port**. After changing the phone IP, orientation or resolution, update .env/restart and recalibrate.

## 5. Start, enrol and calibrate

```powershell
.\scripts\dev.ps1 -Hardware
```

Open http://127.0.0.1:8000 and sign in with your chosen admin password. If the port is occupied by another app, stop that app or use `-Port 8124`; point a notification tunnel to the same selected port.

1. Verify both cameras are OK, firmware BOOT is present and reader count is 2. The browser's preview continuously reads RAM frames; saved gate incident photos still follow third_failure.
2. In Personnel choose Enrol next scanned card, tap a badge on reader #1, enter name/level and save. Enrolment gives harmless PRM feedback and does not open/close a session. In Inventory enrol another tag on reader #2 and save item name, marker ID, minimum level and loan duration. Wait for offline whitelist CURRENT after changes.
3. Create a slot for each item and link its item_id. Print markers using `python tools/print_markers.py --ids 0,20,40,41,42,43 --output data/demo-markers.pdf` for a one-item example. Put item marker 0 on the box; put reveal 20 behind it so it is hidden while the box is present and visible when removed. Keep anchors 40–43 around the shelf on the same plane.
4. In Calibration click **Pause shelf rules**. All configured items must be present and all four anchors visible. Click **Learn shelf**. This learns resting positions and alignment; refine each slot rectangle around the box if necessary. Avoid overlapping regions and include its reveal location.
5. Remove each box during the paused setup, confirm its reveal marker appears inside that rectangle, and **Capture empty reference**. Put it back. Repeat for every slot. Anchors must remain visible throughout. Three anchors support an affine fallback; a true projective homography requires four. The UI reports alignment/residual in System health.
6. With all boxes back, click **Resume shelf rules**. Verify PRESENT for every slot. Do not demonstrate alarms until calibration is stable.
7. Test in order: known badge IN; permitted item ISSUE then lift (MATCHED); item RETURN then replace; low-level badge with restricted item (PRM); unscanned lift while a worker is inside (grace then alarm); acknowledge; restore state; unknown gate badge three times (one laptop photo). Inspect Ledger and Incidents, then test WhatsApp.

## 6. Connect Twilio WhatsApp

See TWILIO_SETUP.md for screenshots-free troubleshooting and signature details. Do this after local RFID/camera rules work:

1. Create your own Twilio account and activate its WhatsApp Sandbox. From the receiving owner's WhatsApp, send the exact `join ...` code to the exact sender shown in your Twilio console. Do not use example phone numbers as credentials.
2. Put SID, token, sender and receiving owner in .env:

```dotenv
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_private_auth_token
TWILIO_WHATSAPP_FROM=whatsapp:+sandbox_sender_number
OWNER_WHATSAPP_TO=whatsapp:+country_code_and_owner_number
PUBLIC_BASE_URL=https://your-public-backend-host
```

3. Twilio needs a public HTTPS backend to fetch the signed incident JPEG. Start a tunnel such as `ngrok http 8000` using its official setup. Copy the generated HTTPS address into PUBLIC_BASE_URL and restart the backend. Tunnel the backend only, never the phone camera. Use strong admin/password signing secrets first. COOKIE_SECURE=true means you must sign into the dashboard through HTTPS rather than plain localhost.
4. In the sandbox's **When a message comes in**, save `https://YOUR-HOST/webhooks/twilio/inbound`, POST. Status callback is `/webhooks/twilio/status` and is also supplied by the app on each send. PUBLIC_BASE_URL must exactly match the URL Twilio calls, or signature validation rejects it.
5. From the owner's phone, send `hello` to the sandbox **after saving the webhook**. System health must show almost 24 hours remaining. Sandbox join and the free-form messaging window are separate checks. Free-form photo alerts require a current 24-hour window; approved out-of-window templates are not implemented.
6. Explicit message test: `python tools/twilio_test.py --photo data/gate-check.jpg`. This sends real messages to your configured owner and may incur provider charges. Success means the receiving WhatsApp actually gets text and photo, not merely a queued SID.
7. Trigger one deliberate third-failure alarm and one illegal shelf removal. The first sends the laptop photo; the second sends the phone shelf photo. Rate limiting suppresses repeats of each kind for 20 seconds. Camera failure yields NO_PHOTO, while the text/incident/local alarm can still work. Expired WhatsApp sessions show FAILED_SESSION_EXPIRED; send hello and verify the inbound webhook.

Official references checked for this implementation: [Twilio Sandbox](https://www.twilio.com/docs/whatsapp/sandbox), [media messages](https://www.twilio.com/docs/whatsapp/tutorial/send-and-receive-media-messages-twilio-api-whatsapp), [signature validation](https://www.twilio.com/docs/usage/security). No credentials or real delivery were available for development verification.

## 7. Offline and failure boundaries

Offline EEPROM authorization and bounded event replay remain available. Active badges/levels and item tags/levels sync to the cache. The controller can enforce cached levels; it cannot run the laptop's loan ledger, zone database, session TTL jobs or shelf vision while the laptop is gone. Offline item events contain a tag hash, not a reliable holder attribution. Review/reconcile offline activity manually after reconnecting; the system does not fabricate online loans from those records. Pending offline events must commit before OFFOK and before cache replacement.

No physical gate barrier, door direction sensor, person detector or facial identification is wired. IN/OUT means a badge-tap declaration, not proof that a body crossed a door. Optional person counting, LCD and ultrasonic sensing remain outside this circuit. Do not claim them in a demo. Notifications require internet; local alarms do not. Physical power loss still loses the board's RAM events/sessions.

For an optional independent notification channel see TELEGRAM_SETUP.md. To demonstrate without hardware, use `scripts/dev.ps1` (without -Hardware) with a separate demo DATA_DIR; all camera/UNO imagery in that mode is synthetic.
