# Current two-reader demonstration

Do CURRENT_SETUP.md first. Use test tags, inform observers before sounding the buzzer, and verify phone/WhatsApp connectivity. Optional people detection is not included. Each RFID tap needs removal/re-presentation and at least 1.5 seconds.

1. Show System health: firmware 2.1, two readers, cache CURRENT, both cameras OK, active WhatsApp window. Explain that the UNO owns immediate alarms and the laptop owns ledger/vision.
2. Scan an authorised badge at reader #1: green IN, session with expiry. A second worker can enter too; explain recent badge attribution. For the simplest demo keep one worker inside.
3. Tap a permitted item's tag at reader #2, lift its box: ISSUE in Ledger and MATCHED in reconciliation, no alarm.
4. Tap that tag again at reader #2 and place the box back: RETURN and RETURN_MATCHED. Confirm AVAILABLE and PRESENT.
5. With a low-level badge inside, scan a higher-level item: PRM and DENIED transaction. Do not remove it yet; show that PRM alone does not cause the gate alarm.
6. Lift that denied item: immediate shelf alarm and phone-camera evidence. Acknowledge, then restore the item with an appropriate RETURN scan and placement.
7. With a worker inside, lift an available item without scanning. Show PREWARN; either scan within ten seconds for LATE_MATCH, or let the deadline expire for UNISSUED and shelf alarm. Returning the box alone does not erase the event.
8. Remove a box without an active session: immediate shelf alarm. Cover the phone: health warning and suspended observation rather than a made-up theft. Restore the camera; modest learned-anchor pose changes should rectify, large/invalid changes require calibration.
9. Tap an unknown badge at reader #1 three times. Show first two failed logs without saved gate photos, then local gate alarm, one saved laptop photo and queued WhatsApp alert. Verify actual receiving-phone text/photo and statuses.
10. Optional controlled PC-loss test: keep UNO powered and use the offline fixture tool without closing its port. Demonstrate cached badge/item permission and commit-before-ACK replay. Review offline activity manually; offline replay is not an attributed online loan ledger. Close the demo by acknowledging alarms, returning all items, checking workers out, stopping the tunnel and stopping the backend.

An overdue example can use a permitted item's two-minute loan duration. Do not alter the PC clock; wait or use the injected-clock software scenario. Record actual times/results in TEST_PLAN.md and MEASUREMENTS.md, with no simulated measurements presented as physical evidence.
