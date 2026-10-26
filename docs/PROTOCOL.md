# Serial protocol v2 (current firmware 2.1)

Current physical roles: rd=0 badge reader D10/D9; rd=1 item reader D4/D5. Firmware 2.1 preserves this wire schema and identifies the changed hardware/failure profile. Only rd=0 denials/timeouts count toward GATE_3_FAIL; item denials still give result feedback. Button is disabled in this circuit (optional A0). Online AUTH decisions are now backed by TTL sessions, levels and issue/return ledger. Historical M2 policy notes below are superseded by CURRENT_SETUP.md where they describe single-session/L1-only behavior.

115200 baud, 8N1, LF-delimited flat ASCII JSON, **at most 96 bytes excluding LF** (CR counts). Uppercase UID hex is 8/14/20 characters. Hashes are exactly 8 uppercase hex characters. Sequences wrap at 16 bits. Both parsers reject malformed/oversized input and duplicate keys. UNO discards oversized lines through LF. No heap strings or JSON library on the board.

v1 wire commands are incompatible. The backend parses an old BOOT only to show **Firmware 2.0 required**, and never grants it online authorization. The old specification is preserved in PROTOCOL_V1.md and tag v1.0. Internal SESSION events remain a temporary backend adapter at M2; they are never emitted by the v2 board. Multi-session/ledger policy begins at M3.

## UNO to PC

| Message/example | Meaning |
|---|---|
| `{"t":"BOOT","fw":"2.0","rst":"PWR","rd":1,"bid":1}` | Reset cause PWR/EXT/BOR/WDT, reader count, persistent boot identifier |
| `{"t":"SCAN","uid":"A1B2C3D4","seq":12,"rd":0}` | Reader 0 or 1; awaiting matching AUTH online |
| `{"t":"FAIL","uid":"DEADBEEF","n":2,"why":"DENY"}` | DENY, TIMEOUT or NSS; count before threshold reset |
| `{"t":"FB","seq":12,"r":"IN","ms":37}` | Output-start firmware latency from SCAN processing; no simulated physical measurements |
| `{"t":"ALARM","why":"DEADMAN"}` | GATE_3_FAIL, SHELF_BREACH, DEADMAN or PC_CMD |
| `{"t":"ALARM_OFF","by":"BTN"}` | TIMEOUT, ACK or enabled button long press |
| `{"t":"PW","st":"ON"}` | ON, OFF or ESC; ESC precedes one DEADMAN alarm using shelf pattern |
| `{"t":"HB","up":12345,"n":1,"pcok":1,"ram":1432,"lp":1840,"off":0}` | Every 2 s: millis, session count, PC watchdog, free RAM, maximum loop µs since previous HB, pending offline records |
| `{"t":"BTN","k":"S"}` | S short release or L long release |
| `{"t":"OFF","id":1,"bid":1,"h":"1234ABCD","e":"IN","ago":4}` | At-least-once offline replay; event IN/OUT/ISS/DEN, seconds ago |
| `{"t":"WLOK","n":2}` | EEPROM whitelist committed |
| `{"t":"WLERR","why":"CRC"}` | BUSY, COUNT, CRC, DUP, STATE or FULL; old committed whitelist remains usable on rejected upload |

## PC to UNO

| Message/example | Meaning |
|---|---|
| `{"t":"AUTH","seq":12,"r":"IN","n":1}` | Result and authoritative open-session count; no local online toggle/BUSY |
| `{"t":"HB","n":1}` / `{"t":"SYNC","n":1}` | Renew 6 s watchdog / mirror count (0–8) |
| `{"t":"PW","on":1,"s":10}` / `{"t":"PW","on":0}` | Start grace or cancel; a later start cannot extend the earliest active deadline |
| `{"t":"ALARM","on":1,"why":"SHELF_BREACH"}` | Immediate reason-coded local alarm |
| `{"t":"ACK"}` | Stop alarm and prewarning |
| `{"t":"CFG","fail_limit":3,"window_s":60,"alarm_s":30}` | Limits 1–20 / 1–3600 / 1–3600 |
| `{"t":"TEST","what":"green"}` | One-second green/red/buzzer test |
| `{"t":"WL","op":"CLR","n":2}` | Start RAM staging for expected entry count (0–100) |
| `{"t":"WL","op":"ADD","h":"1234ABCD","lv":2,"it":0}` | Hash, level 1–3, is-item 0/1; duplicate hashes refused |
| `{"t":"WL","op":"END","n":2,"ck":12345}` | Validate count/CRC before any whitelist EEPROM writes |
| `{"t":"OFFOK","id":1}` | Acknowledge oldest offline record only after durable PC commit |

## Feedback table

| Result | Green / red | Buzzer | Failure counter |
|---|---|---|---|
| IN | Green steady while n>0 | 80 ms beep | Reset |
| OUT | Two green 150 ms on/off pulses | Two 80 ms beeps, 120 ms gap | Reset |
| ISS | Three green 70 ms on/off pulses | One 80 ms beep | Reset |
| RET | Two green 250 ms on/off pulses | One 80 ms beep | Reset |
| DEN | Red 2 s | None | Increment |
| NSS | Red 2 s | None | Increment |
| PRM | Red 2 s | Two 80 ms beeps, 120 ms gap | Unchanged |

The table is stored in PROGMEM. Success resets consecutive failures; 3 failures within 60 s of the first alarms and resets count. No AUTH by 1000 ms counts TIMEOUT. A PC-lost tap uses EEPROM policy at M2 rather than waiting for AUTH. Debounce is 1.5 s per reader's last UID. A pending online request prevents overlapping scans.

PW red flashes at 1 Hz and chirps for 80 ms each second; at its deadline it escalates locally even with PC dead. Alarm red flashes 100 ms on/off. GATE_3_FAIL/PC_CMD buzz 200/200 ms; SHELF_BREACH/DEADMAN buzz 600/300 ms, starting immediately. Button D4 uses INPUT_PULLUP and 30 ms debounce. Short release mutes only sound for 30 s; a >=1.5 s hold then release ACKs if BTN_ACK_ENABLED=1. Alarm/feedback timers use unsigned subtraction across millis rollover. Alarm output takes priority over tests and feedback; mute silences sound but not visual alarm/logging.

## Hash, EEPROM and replay contract

FNV-1a starts 2166136261 and for each **uppercase UID character byte** applies `(hash XOR byte) * 16777619 modulo 2^32`. Hashing raw RFID bytes would be incompatible. CRC16-CCITT-FALSE uses polynomial 0x1021, initial 0xFFFF, no reflection/final XOR; `123456789` -> 0x29B1. CRC covers `[version=2,count]` followed by each hash as four **little-endian bytes** and flag byte `(level & 3) | (is_item ? 0x80 : 0)` in upload order.

EEPROM addresses: 0–1 magic W2; 2 version; 3 count; 4 onward packed entries, then two little-endian CRC bytes. Maximum end is byte 505. A separate two-slot boot counter journal uses 1008–1023 (each slot has uint32 counter and its complement). A torn journal update retains the other valid slot; the new boot identifier is written before BOOT/scans. Whitelist commit invalidates magic, uses EEPROM.update, and publishes magic last. Interrupted power during commit fails closed on reboot. WL CLR/ADD never write EEPROM. Byte-identical valid uploads skip EEPROM writes at END. BUSY protects active alarm/PW/auth or unacknowledged replay. Staging is discarded if PC disappears; the previous committed list stays intact.

Offline mode permits EEPROM badges into an in-RAM set of at most eight hashes and item ISS when the attributed badge meets level. Recent badge within 30 s wins; otherwise a sole offline badge is used; ambiguous/no owner gives NSS. Sixteen RAM log entries are retained until ACK, oldest-first replay each second. A full ring denies new offline operations rather than overwriting history. The PC commits/deduplicates by configured board identity, boot id and event id before OFFOK. Power loss destroys the RAM log and offline session identities. SYNC n cannot restore badge identities; a restored PC session must be tapped again to establish offline identity. Offline shelf alarms and an audited offline item ledger are unavailable.

Run `python tools/protocol_conformance.py --simulate`; real mode `--port COM3` with the app stopped. M2 hardware instructions explain the explicit whitelist fixture test and normal cache synchronization.
