# Serial protocol v1.0

## Framing

115200 baud, 8 data bits, no parity, 1 stop bit, no flow control. UTF-8/ASCII newline-delimited flat JSON objects; send one object per line. Maximum **96 bytes excluding LF**, with optional CR counted in the limit. Compact JSON is preferred. UID is uppercase hex without spaces: 8, 14 or 20 characters (4, 7 or 10 bytes). Sequences are unsigned 16-bit numbers and wrap from 65535 to 0. Match AUTH against the pending sequence, never against a previous scan.

UNO stores at most 96 bytes, discards an oversized line through its newline, and resumes on the next line. Invalid/unknown/duplicate JSON fields are rejected by the UNO's bounded parser. It accepts only unescaped strings and unsigned integers. The PC framing parser raises ValueError for invalid JSON, oversized lines, unknown messages, or invalid common fields; the serial reader increments its malformed counter and continues. Never include passwords or credentials in the protocol.

## UNO to laptop

| Message | Meaning |
|---|---|
| `{"t":"BOOT","fw":"1.0"}` | Reset/boot; laptop sends CFG and SYNC |
| `{"t":"SCAN","uid":"A1B2C3D4","seq":12}` | New scan, awaiting AUTH for up to 1000 ms |
| `{"t":"SESSION","state":"IN","uid":"A1B2C3D4"}` | Worker checked in |
| `{"t":"SESSION","state":"OUT","uid":"A1B2C3D4"}` | Same worker checked out |
| `{"t":"FAIL","uid":"DEADBEEF","n":2,"why":"DENY"}` | Denied or TIMEOUT; n is count before threshold reset |
| `{"t":"BUSY","uid":"11223344"}` | Valid different worker while occupied; current session stays |
| `{"t":"ALARM","why":"GATE_3_FAIL"}` | Gate threshold; other reasons SHELF_BREACH or PC_CMD |
| `{"t":"ALARM_OFF","by":"TIMEOUT"}` | Alarm ended by timeout or ACK |
| `{"t":"HB","up":12345,"s":"IN","pcok":1}` | Every 2 s; millis uptime, session state, laptop watchdog |

## Laptop to UNO

| Message | Action |
|---|---|
| `{"t":"AUTH","seq":12,"ok":1}` | Authorize matching pending scan; ok=0 denies |
| `{"t":"REMOVAL","slot":2}` | Sound SHELF_BREACH only when UNO session is OUT |
| `{"t":"ACK"}` | Silence alarm immediately, emit ALARM_OFF ACK |
| `{"t":"HB"}` | Every 2 s; renew PC watchdog |
| `{"t":"SYNC","state":"IN","uid":"A1B2C3D4"}` | Restore open worker after laptop/board restart |
| `{"t":"SYNC","state":"OUT"}` | Clear session |
| `{"t":"CFG","fail_limit":3,"window_s":60,"alarm_s":30}` | Volatile configuration; resent on reconnect |
| `{"t":"TEST","what":"green"}` | One-second output test: green, red, buzzer |
| `{"t":"ALARM","on":1}` | Manual PC_CMD alarm |

CFG accepts fail_limit 1–20, window_s/alarm_s 1–3600. Alarm and authentication defaults in config.h match .env.example. AUTH_TIMEOUT_MS, HEARTBEAT_MS and PC_LOST_MS are compile-time UNO constants; changing laptop heartbeat alone does not recompile firmware. SYNC is trusted from the local serial owner. Opening the serial port normally resets an UNO: wait for BOOT and resynchronize. Only one program may open the port.

## Timing and transitions

```text
OUT + valid A -> SESSION IN A -> green steady
IN A + valid A -> SESSION OUT A -> two green flashes
IN A + valid B -> BUSY B (failure count resets)
SCAN -> no matching AUTH in 1 s -> FAIL TIMEOUT (default compile flag)
DENY/TIMEOUT -> red 2 s, consecutive counter increments
third failure within 60 s of first -> alarm 30 s, counter resets
any valid scan / expired window -> counter resets
OUT + REMOVAL -> alarm SHELF_BREACH
IN + REMOVAL -> ignored
alarm + ACK / timeout -> ALARM_OFF
no PC HB for 6 s -> alternate red/green; AUTH refused until HB returns
```

Alarm output priority overrides watchdog/test indications. Alarm buzzer alternates 200 ms on/off and red blinks every 100 ms. Timer comparisons use unsigned subtraction for millis rollover. Remove and re-present a card; repeated identical reads within 1.5 s are ignored.

## Example exchange

```text
UNO > {"t":"SCAN","uid":"A1B2C3D4","seq":12}
PC  > {"t":"AUTH","seq":12,"ok":1}
UNO > {"t":"SESSION","state":"IN","uid":"A1B2C3D4"}
PC  > {"t":"REMOVAL","slot":2}
      (no alarm because worker is IN)
```

Run `python tools/protocol_conformance.py --simulate` first, then `--port COM3` (or `/dev/ttyACM0`) with the app stopped. The real-board script asks for physical card taps and asserts matching replies. It does not substitute synthetic SCAN messages for real RFID reads.
