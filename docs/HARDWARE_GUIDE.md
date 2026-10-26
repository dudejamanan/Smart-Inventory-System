# Hardware guide

**Current supplied circuit:** use CURRENT_SETUP.md. Reader #1 SS/RST D10/D9; reader #2 D4/D5; button disabled (optional A0). Main firmware 2.1 defaults to two readers. Earlier M2 D5/D3 + D4-button wiring does not match this circuit. Shared power is subject to the actual 3.3 V supply current budget; verify both modules and level shifting before powering.

**v2 M2 users:** this remains the v1 assembly/reference guide. Follow [V2_HARDWARE_CHECKPOINT](V2_HARDWARE_CHECKPOINT.md) for authoritative v2 pin additions, two-reader power/dividers, button, watchdog, uploads, offline/replay and exact ordered tests. The old BUSY/session and protocol examples below apply only to tag v1.0.

## 1. Parts and vocabulary

A **pin** is an electrical connection on a board. **GND** is the shared zero-volt reference. A **breadboard** connects holes internally so you can prototype without soldering. An **LED** is a light-emitting diode; it passes current in one direction. A **resistor** limits current. An **RFID UID** is a card's identifier; this project checks it against a whitelist.

| Quantity | Part | Exact specification / purpose |
|---|---|---|
| 1 | Arduino UNO R3 or compatible | ATmega328P, 5 V logic, USB cable matching board (usually USB-B) |
| 1 | RC522 module | MFRC522, 13.56 MHz, 3.3 V supply, SPI header with SDA/SCK/MOSI/MISO/IRQ/GND/RST/3.3V |
| 2+ | RFID cards/tags | Compatible 13.56 MHz ISO/IEC 14443A tags; not 125 kHz tags |
| 1 each | Green and red LEDs | Standard 3 or 5 mm, about 2 V forward drop |
| 2 | LED resistors | 220 ohm, 1/4 W, ±5% |
| 1 | Low-current active piezo buzzer | 5 V rated, signal current below 15 mA for direct-pin test; passive piezo alternative supported |
| 1 | Breadboard | At least 400 tie points |
| ~25 | Jumper leads | Male–male and male–female as needed, 10–20 cm |
| 4 each | Divider resistors | 1 kilo-ohm and 2 kilo-ohm, 1/4 W, ±5%, for SS/SCK/MOSI/RST |
| 1 | Laptop | USB port, webcam, Python 3.11 and Node 22+ |
| 1 | Phone with camera | Wi-Fi, MJPEG streaming app, charger |
| 1 | Phone mount | Stable clamp/tripod; do not hand-hold during calibration |
| 3+ | Boxes and printed markers | Matte paper, black-and-white print at actual size, 4–5 cm black marker squares |
| 1 | Steady lamp | Diffuse lighting; avoid glare and backlight |

Optional: multimeter (check voltage/continuity), 4-channel unidirectional 5 V to 3.3 V logic level shifter suitable for SPI, spare resistors, USB extension, matte tape, logic analyzer, powered USB hub. For a buzzer drawing more than 15 mA, use an NPN transistor stage (e.g. 2N2222, 1 kilo-ohm base resistor, common ground), and a flyback diode for an inductive magnetic buzzer. Ask your lab instructor to check that circuit before use. A three-pin buzzer module may already include a transistor; follow its marked VCC/GND/S input ratings. HC-SR04 is not used.

## 2. Pin-by-pin wiring

**Disconnect USB before touching wires. Never connect RC522 VCC to 5 V.** Read labels printed on the actual board, not only wire colors. Some RC522 modules label their SPI chip-select pin SDA; it is still SS here, not an I²C data line.

| RC522 pin | UNO connection | Notes |
|---|---|---|
| SDA / SS | D10 through 1k/2k divider | UNO output -> reader input |
| SCK | D13 through divider | SPI clock |
| MOSI | D11 through divider | Master output to reader |
| MISO | D12 directly | Reader 3.3 V output to UNO input |
| RST | D9 through divider | Reset input |
| VCC / 3.3V | UNO 3.3V | Never 5V; check label carefully |
| GND | UNO GND / common ground rail | Required for all circuits |
| IRQ | Not connected | Not used |

| Other part | Connection |
|---|---|
| Green LED | D7 -> 220 ohm -> long leg/anode; short leg/cathode -> GND |
| Red LED | D8 -> 220 ohm -> long leg/anode; short leg/cathode -> GND |
| Low-current buzzer + | D6 (or transistor input for larger buzzer) |
| Buzzer − | GND |

```text
UNO                    breadboard                         RC522
3.3V ------------------ +3.3 rail ------------------------- VCC
GND ------------------- GND rail -------------------------- GND

D10 ---- [1k] ----+---------------------------------------- SDA/SS
                 +---- [2k] ---- GND
D13 ---- [1k] ----+---------------------------------------- SCK
                 +---- [2k] ---- GND
D11 ---- [1k] ----+---------------------------------------- MOSI
                 +---- [2k] ---- GND
D9  ---- [1k] ----+---------------------------------------- RST
                 +---- [2k] ---- GND
D12 ------------------------------------------------------ MISO

D7 ---- [220 ohm] ---- |>| green ---- GND
D8 ---- [220 ohm] ---- |>| red   ---- GND
D6 ------------------ buzzer +
GND ----------------- buzzer -
```

Breadboard power rails may be split halfway: use continuity mode with power OFF to check. A row of five holes on one side of the center trench is usually connected; opposite sides are separate. Place the LED legs in different connected rows. The `+` meeting point in each divider diagram is one node: reader input and both resistors meet there. Repeat the divider independently on all four signals.

## 3. RC522 voltage and level shifting

The UNO outputs about 5 V on high digital outputs; the reader's chip uses 3.3 V logic. A voltage divider uses two resistors to lower a voltage: `5 * 2000 / (1000 + 2000) = 3.33 V`. Connect a 1k resistor from the UNO pin to the reader-input node, and a 2k resistor from that node to GND. Do this for SCK, MOSI, SS and RST. No divider on MISO: it already comes from the reader at 3.3 V. No divider in the power feed: supply VCC from the UNO's regulated 3.3 V pin.

A proper SPI-rated level shifter is preferable for reliable, faster edges and longer wires. Many cheap bidirectional MOSFET I²C level shifters are not ideal for SPI clocks; check the module's speed/direction specification. Keep wires short. Dividers are a student-friendly starting point but capacitance can distort fast clocks. If reads are intermittent, shorten wiring and use a suitable buffer/shifter rather than removing protection.

Some tutorials connect UNO signal pins directly because certain breakout boards appear to tolerate it. That is not a guarantee of the MFRC522 input ratings: it can cause intermittent failures or damage. Use the recommended dividers/shifter and 3.3 V supply. The library's official repository discusses voltage and wiring: https://github.com/miguelbalboa/rfid .

## 4. LEDs and buzzer

LED polarity: long leg = anode (+); short leg or flat side of the plastic = cathode (−). With about 2 V across a red/green LED, `(5-2)/220 ≈ 0.014 A`, or 14 mA, is a reasonable current. Never omit the resistor. The resistor can be on either side of an LED as long as it is in series.

An **active buzzer** has its own oscillator and sounds with steady rated DC. A **passive piezo** needs pulses; firmware uses `tone(6, 2200)` for it. Check the product label/datasheet first. If a rated, low-current two-pin device sounds from a brief 5 V test through an appropriate driver, it is active; a passive piezo may only click. Do not trial unknown or high-current devices directly on an UNO pin. Main firmware defaults `BUZZER_ACTIVE=1`. Change to 0 for passive in config.h, and use the same flag for led_buzzer_test. Success: the test has one second of green, one of red, one of sound, then one silent second, repeating.

## 5. Assemble safely and check power

1. Unplug USB. Put the UNO and breadboard on a dry, nonconductive desk. Touch grounded metal before handling the reader.
2. Connect common GND first. Build the four dividers, then connect RC522 data pins. Check each against section 2.
3. Connect the 3.3 V rail to RC522 VCC. Inspect that there is **no** wire from 5 V to the reader.
4. Wire each LED through its own 220-ohm resistor. Wire the correct buzzer/driver.
5. Ask a lab partner/instructor to compare all connections with the table. Check for loose strands or power-to-ground shorts.
6. Plug in USB. A board power LED should light; nothing should become hot. If anything heats, smells, or USB disconnects repeatedly, unplug immediately and inspect.
7. With a multimeter on DC volts, measure RC522 VCC to GND: approximately 3.3 V. Check divider nodes if possible. Success: correct supply and no hot components.
8. Upload the reader test, then output test, then main firmware as described below. Main firmware alternates red/green after six seconds without PC heartbeats; that indicates an absent laptop app, not necessarily bad wiring.

## 6. Install tools and upload

1. Install Arduino IDE 2 from [Arduino software](https://www.arduino.cc/en/software). Connect the UNO by USB. If your compatible board uses CH340/CP210x USB, obtain its driver from the board/USB-chip manufacturer's site; avoid random driver download sites.
2. In IDE Library Manager, search **MFRC522** by GithubCommunity/miguelbalboa and install version **1.4.12** (or the exact version in VERIFICATION if newer was used). SPI is bundled with the AVR core. Select **Arduino UNO**, not a Mega/Nano unless changing the design.
3. Select the USB serial port under Tools > Port. On Windows identify it by unplugging/replugging and watching Device Manager > Ports; e.g. COM3. On Linux it is often `/dev/ttyACM0` or `/dev/ttyUSB0`; on macOS `/dev/cu.usbmodem…`.
4. Stop the laptop app and close all serial tools. Copy `firmware/tests/rfid_test.ino` into a folder named `rfid_test`; open it in IDE and upload. Select Serial Monitor **115200 baud**. Bring a compatible tag within about 1–3 cm, then remove it. Success: a stable uppercase UID appears each time you re-present the card. Record it exactly; no spaces.
5. Close Serial Monitor. Put `led_buzzer_test.ino` into a matching folder, choose its active/passive setting, and upload. Success: green/red/buzzer/silence cycle; no constant buzzer. Fix hardware before continuing.
6. Open `firmware/arduino_gate/arduino_gate.ino` (config.h stays next to it). Verify pin values and buzzer flag. Upload. Success: monitor shows `{"t":"BOOT","fw":"1.0"}` and heartbeat JSON every two seconds. Close monitor before starting the app.
7. CLI alternative after [arduino-cli installation](https://arduino.github.io/arduino-cli/latest/installation/): run `arduino-cli core update-index`, `arduino-cli core install arduino:avr@1.8.6`, `arduino-cli lib install "MFRC522@1.4.12"`, then `arduino-cli compile --fqbn arduino:avr:uno firmware/arduino_gate`, followed by `arduino-cli upload -p COM3 --fqbn arduino:avr:uno firmware/arduino_gate`. Substitute your port. Success: compile prints flash/RAM usage, upload reports success, then BOOT appears.
8. Linux permission issue: add your user to the distribution's serial-access group (often `dialout`), log out/in, then retry. Avoid running the dashboard as root. On Windows, make sure a charge-only USB cable is not being used.

## 7. Enrol cards and verify gate behavior

1. Configure SERIAL_PORT in .env and start real mode (SETUP_GUIDE). Wait for System health > Serial connected.
2. Sign in, open Personnel, choose **Enrol next scanned card**, then tap a card. The UID fills the form. This scan is still denied until the new record is saved; enrolment never silently authorizes a stranger.
3. Enter the person's name, leave Active checked, and save. Or type the UID from the reader test manually.
4. Wait 1.5 s and tap again. Success: SESSION IN, green stays on, dashboard shows the worker.
5. Remove and tap the same card again. Success: SESSION OUT, two green flashes, worker clears. A different valid card during an open session shows BUSY.
6. Test an unknown card once: red for 2 s and a failed scan/photo. Three failed re-presentations within 60 s: buzzer pattern, fast red blink, incident. Acknowledge on dashboard to silence. Always warn people nearby before testing the buzzer.

## 8. Gate layout

Mount the reader beside the laptop webcam so the worker faces the camera while tapping. Use the camera at approximately face height, typically 1.4–1.7 m from the floor depending on users. Start with the face 0.6–1 m from the webcam; adjust while watching its preview until head and shoulders fit with margin. Keep the RC522 within comfortable reach and tags within 1–3 cm. Do not lengthen SPI leads across the room to reach the camera; position the laptop/UNO together. Illuminate faces from the front with a diffuse lamp. Avoid a bright window behind the worker. Obtain participants' consent before saving demonstration photos.

## 9. Shelf layout

1. Clamp the phone about 40–60 cm from the shelf as a starting point; adjust until every box and anchor is in frame. Aim squarely at marker faces. Keep the mount outside paths where it can be bumped.
2. Print 4–5 cm markers using print_markers.py at 100% scale. Measure the black square with a ruler. Leave a white border, print on matte paper and tape flat on box fronts. Avoid glossy tape across the marker.
3. Give every box a different item ID 0–29. Fix anchor IDs 40–49 to the shelf structure, never to removable boxes. Include at least two well-separated anchors if using movement health.
4. Use a steady lamp; avoid flickering light, strong shadows and backlight. Lock phone focus/exposure/white balance if the app permits. Keep marker squares large and sharp enough in the actual 960-pixel-wide processed image.
5. Fix the phone orientation and preview it before drawing ROIs. Capture empty references with **each box removed and hands out of frame**. Recalibrate after moving the phone, lamp or shelf. Success: boxes show PRESENT, removed slots ABSENT, a hand over a marker OCCLUDED.

## 10. Troubleshooting

| Symptom | Check / fix | Success |
|---|---|---|
| No serial data | Correct data USB cable/port/driver; close other tools; upload sketch | BOOT then HB |
| Wrong baud | Set every tool and .env to 115200, firmware SERIAL_BAUD too | Readable JSON |
| Garbled output | 115200, correct board clock/core, common ground, short leads | Stable lines |
| RC522 never reads | 3.3 V, common GND, SDA=D10 not I²C, SPI pins, compatible 13.56 MHz card | UID repeats consistently |
| Reader intermittent | Shorten wires, inspect divider junctions/power, use SPI-rated shifter, re-present card after removing | Repeated reliable scans |
| LED dark | Polarity, separate breadboard rows, 220-ohm resistor, correct D7/D8 | Output test lights it |
| Buzzer silent | D6/GND, active/passive flag, polarity, driver and current rating | One-second sound in test |
| Buzzer constant | Wrong buzzer type/driver, active alarm, missing ACK; check alarm state | Silent after ACK/test ends |
| Phone stream lags | Same Wi-Fi, reduce resolution/FPS, close other viewers, disable power saving | Recent frames and health OK |
| False removal alarms | Re-capture empty references, stabilize lighting, widen ROI correctly, tune diff threshold/debounce | Hand -> OCCLUDED, empty -> ABSENT |
| Camera MOVED | Realign phone/anchors, restart baseline only after checking scene | Correct marker alignment and OK |
| Twilio 63016 | Owner sends inbound message; verify signed inbound webhook reaches app | Timer positive and delivered message |
| Twilio 63015 | Owner rejoins the correct sandbox code | Sandbox join confirmation |
| Media fails | PUBLIC_BASE_URL HTTPS reachable externally, valid token, no tunnel login page | Phone receives photo |
| Webhook 403 | Token/public URL wrong or URL changed; do not disable signature checking | Valid callback accepted |

## 11. Safety

Use USB power only for this prototype. No mains wiring, door-lock solenoids or high-current devices. Unplug before rewiring; no hot-plugging reader wires. Do not short 3.3 V/5 V rails. Keep liquids and metal scraps away, protect exposed leads, and discharge static before touching boards. Do not leave the powered prototype unattended. Limit buzzer exposure and tell nearby people before alarm tests. Keep the phone mount secure and charging cable out of walking routes.
