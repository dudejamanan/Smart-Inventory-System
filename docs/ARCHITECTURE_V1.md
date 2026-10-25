# Architecture

## Ownership and failure boundaries

```text
RC522 -- SPI --> UNO state machine -- D7/D8/D6 --> lights / buzzer
                    | 115200 newline JSON
                    v
            serial reader + writer (PC heartbeat)
              | AUTH from in-memory whitelist (first)
              | event queue (second)
              v
   rules engine --> SQLite WAL --> REST / WebSocket --> React console
       |                 ^
       +--> gate photo worker --> sharpest JPEG
       +--> notification queue --> Twilio --> owner's WhatsApp
       +--> evidence workers --> JPEG / MP4 + SHA-256
       ^
   vision thread <-- latest frame / 5-second ring <-- phone MJPEG grabber
```

The UNO decides when to sound, including a shelf REMOVAL command. Failure of Twilio, SQLite or either camera cannot disable its autonomous failure counter, authentication timeout, alarm timeout, or watchdog. The PC can only report a shelf removal when vision has a usable source; camera failure creates a warning rather than inventing a removal. A lost laptop cannot discover new shelf breaches; the gate continues to deny/time out and alarm locally.

## Concurrency and lifecycle

One process owns hardware. Serial reading and writing use independent threads; the reader checks the in-memory whitelist and queues AUTH before durable event processing. A bounded event queue feeds the engine. The engine serializes session and incident decisions with an RLock. SQLite sessions are short-lived and never shared between threads. Separate gate photo, evidence, notification, vision, and frame-grabber workers isolate slow I/O. WebSocket clients have bounded queues and receive periodic status messages; slow clients lose old updates rather than blocking hardware.

Startup creates tables, applies safe settings-table overrides, reloads the open session, then starts grabbers, workers and serial. Every connection/BOOT sends CFG and SYNC. An explicit demo seed exists; simulation uses it automatically. Shutdown stops vision and serial first, drains event work, joins capture/evidence/notifier workers, releases cameras and disposes the database. Camera network reads use OpenCV timeout properties; USB driver behavior is platform dependent.

## Vision state machine

Each slot has a normalized ROI and marker ID. A marker's center must be inside that ROI. A visible marker votes PRESENT. Without a marker, a blurred grayscale difference against the saved empty ROI votes ABSENT below the configured threshold and OCCLUDED above it. Without an empty reference it votes UNKNOWN. At least N votes in the last M frames establish a state. Defaults: 4/5 at 10 fps. Camera faults suppress reliable slot votes to UNKNOWN. OCCLUDED lasting more than 2 s yields a warning while unattended, once per occlusion episode.

Anchor centers observed at startup provide a relative movement baseline. Movement or disappearance persisting for 3 s yields MOVED. This is a camera-health heuristic, not geometric pose calibration. Restarting establishes a new baseline; physically verify it before the demo.

## Security and evidence

The single admin password is compared in constant time. Signed HttpOnly cookies expire after eight hours; mutations require a custom request header and same-origin requests. WebSockets require a session and validate Origin. Real mode requires configured password/cookie/media secrets. Public media is limited to a signed, expiring JPEG under the data directory. The rest of the evidence is authenticated. Inbound/status Twilio hooks validate the provider signature using the exact configured public HTTPS URL.

Evidence hashes establish file integrity relative to the recorded hash, not legal proof of custody. Use system-clock synchronization. Photos and clips expire after 30 days unless their incident is marked Keep; history rows remain and expired evidence is marked unavailable. Empty-reference calibration files are operational configuration and must remain available.

## Scope

The system is a student prototype with one gate, one active worker, and one shelf camera. RFID UIDs are identifiers, not cryptographic credentials. Do not use this as a production physical lock. No face recognition is performed. Optional zone columns are included from the beginning; see DECISIONS for the final implementation status.
