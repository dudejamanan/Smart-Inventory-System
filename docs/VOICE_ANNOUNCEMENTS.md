# Local voice announcements

Added 2026-10-28 using pyttsx3 2.99 and the Windows SAPI5 voices installed on the laptop. No cloud speech service, microphone recording or internet connection is used. Audio plays from the backend laptop, not the dashboard browser or phone.

| Trigger | Spoken message |
|---|---|
| Confirmed badge IN | Access granted. Welcome. |
| Confirmed badge OUT | Checked out. Goodbye. |
| Confirmed item ISSUE | Permission granted. Item issued. |
| Confirmed item RETURN | Item returned. Thank you. |
| Unknown/inactive tag | Access denied. |
| Wrong reader/clearance/capacity refusal | Permission denied. Check the reader and your clearance. |
| Item scan without attributed session | Scan your badge before scanning an item. |
| Tag enrolment capture | Tag captured. Save it to complete enrolment. |
| Removal grace period begins | Warning. Scan the item before the grace period expires. |
| Late match cancels warning | Item scan matched. Warning cleared. |
| Three-failure alarm | Security alarm. Three failed access attempts. |
| Shelf/dead-man alarm | Security alarm. Unauthorised shelf removal. |
| Acknowledged alarm | Alarm acknowledged. |
| Alarm timeout | Alarm sound stopped. Please review the incident. |

Additional short prompts cover expired sessions, overdue items, missing return scans/placements, and camera/USB health transitions. Initial health states, heartbeat telemetry and historical offline replay do not chatter. Names, UIDs, camera credentials, notification content and arbitrary external text are never read aloud. Speech is feedback, not an access-control decision or physical proof that someone entered.

## Controls

- Use **Mute voice / Enable voice** in the dashboard header.
- In Settings, TTS rate is 80–300 words/minute; volume is 0–1. A blank voice uses the Windows default. A voice can be selected by installed voice name or ID; installed voices are listed in the authenticated `/api/status` speech diagnostics.
- Use **System health → Test voice**. This plays example words only; it does not raise a real Arduino alarm or send notifications.
- Settings apply immediately. Muting cancels queued/current speech on the audio worker. Simulation is silent unless TTS_IN_SIMULATION=true is deliberately set before startup.

Optional .env values:

```dotenv
TTS_ENABLED=true
TTS_RATE=175
TTS_VOLUME=0.9
TTS_VOICE=
TTS_IN_SIMULATION=false
TTS_HEALTH_ANNOUNCEMENTS=true
```

Install the pinned backend lockfile normally. An independent explicit audio check is:

```powershell
.\.venv\Scripts\python tools/tts_test.py
```

Windows voices detected: Microsoft David Desktop and Microsoft Zira Desktop; the platform default was used for the audible test. On Linux pyttsx3 requires a working local eSpeak installation/audio output; that platform was not physically tested. This change was verified on Python 3.11/Windows.

## Isolation and verification

One dedicated worker creates, pumps and stops pyttsx3/SAPI and initializes/releases Windows COM on that same thread. Serial and timer threads only enqueue fixed phrases after controller dispatch. A bounded 16-message queue drops expired routine messages; critical alarms discard stale successes and preempt lower-priority speech. Alarm echoes are deduplicated and ACK removes stale alarm/prewarning speech. Driver failure/timeout is visible in System health and never disables the UNO buzzer, camera pipeline or RFID rules.

The pyttsx3 external event loop is used so mute and alarm preemption can be processed by the same owning thread without a blocking runAndWait call. It preserves one engine across announcements. Failed audio retries are bounded; Test voice explicitly retries after a driver/voice fix. The safety mechanism remains the UNO alarm, including when the laptop/audio service is off.

Verification: the local worker completed a real SAPI5 speech test and the user explicitly confirmed hearing the voice clearly. Automated tests cover all result phrases, enrolment, duplicate feedback, priority, stale-message cancellation, mute, driver failure, owner-thread creation/use, warning/health prompts, API settings and dispatch isolation. Full suite: 94 passed in 44.26 s (one existing dependency warning). Frontend locked install/build and pip dependency checks passed. No physical GPIO or firmware change was required for speech.

References: [pyttsx3 package](https://pypi.org/project/pyttsx3/), [engine/event-loop API](https://pyttsx3.readthedocs.io/en/latest/engine.html). Community research was attempted but the installed connector required its account connection; no unsupported community citations are used.

Live activation: restarted the single hardware backend; COM11 reported firmware 2.2 and connected=true. Speech reported ready=true, no error, and completed startup/camera announcements. Authenticated mute/enable API checks passed and speech was left enabled.
