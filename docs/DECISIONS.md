# Decisions

1. Build at the existing repository root (`D:/inventorySystem`), rather than nesting another repository.
2. Python 3.11 is the supported development runtime (installed locally); Python 3.14 is not used because pinned OpenCV wheels target earlier runtimes.
3. A single FastAPI process owns hardware. Never run multiple Uvicorn workers. SQLite uses WAL, a busy timeout, and short per-operation sessions.
4. UNO owns all buzzer decisions. Serial authentication is sent before database event insertion or camera work. Notification and evidence queues run independently.
5. Simulation uses the real vision pipeline and a clock-injected firmware port; it never claims to measure electrical latency.
6. Demo data is created only in simulation or via the explicit seed command. Blank real installations start without authorized cards.
7. Official references checked on 2026-10-24: [MFRC522](https://github.com/miguelbalboa/rfid), [OpenCV](https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html), [Twilio request validation](https://www.twilio.com/docs/usage/security), [Twilio 63016](https://www.twilio.com/docs/api/errors/63016). New OpenCV uses ArucoDetector/generateImageMarker; compatibility branches support detectMarkers/drawMarker. Twilio error 63016 means outside the 24-hour service window; this course project uses free-form sandbox messages, not template campaigns.
8. DevRelay community searches and event lookup were attempted but refused because the account is not connected. No community claims or links are fabricated.
