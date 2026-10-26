"""v2 command conformance. Real board mode needs main sketch and physical card taps."""

import argparse
import time
from common import connect, wait_for, encode
from app.sim.arduino import SimulatedArduino
from app.services.protocol import fnv1a, whitelist_messages


def offline_fixture(board, badge, item, replay_dir="data/hardware-replay"):
    """Explicit destructive test fixture; backend will replace it on next normal sync."""
    if badge == item:
        raise ValueError("Badge and item must be different tags")
    board.write(encode({"t": "HB", "n": 0}))  # restore PC presence after dead-man test
    for message in whitelist_messages(
        [(fnv1a(badge), 2, False), (fnv1a(item), 1, True)]
    ):
        board.write(encode(message))
        time.sleep(0.04)
    assert wait_for(board, lambda e: e["t"] == "WLOK")["n"] == 2
    print("PASS EEPROM upload count/CRC. No heartbeats now; keep USB connected.")
    wait_for(board, lambda e: e["t"] == "HB" and e["pcok"] == 0, 10, heartbeat=False)
    for uid, result in [(badge, "IN"), (item, "ISS"), (badge, "OUT")]:
        reader = 2 if uid == item else 1
        print(
            f"Offline: tap {uid} on reader #{reader} for {result}; remove cards between taps."
        )
        scan = wait_for(board, lambda e: e["t"] == "SCAN", 25, heartbeat=False)
        assert scan["uid"] == uid, f"Expected {uid}, saw {scan['uid']}"
        fb = wait_for(
            board, lambda e: e["t"] == "FB" and e["seq"] == scan["seq"], heartbeat=False
        )
        assert fb["r"] == result, fb
        print("PASS offline", result, fb)
    from pathlib import Path
    from app.config import Config
    from app.db.store import Store
    from app.db.models import OfflineRecord
    from app.services.offline import OfflineCoordinator
    from sqlalchemy import select

    class Link:
        connected = True

        def send(self, message):
            board.write(encode(message))

    store = Store(Config(data_dir=Path(replay_dir)))
    coordinator = OfflineCoordinator(store, Link(), lambda: [])
    board.write(encode({"t": "HB", "n": 0}))
    seen = set()
    while len(seen) < 3:
        event = wait_for(board, lambda e: e["t"] == "OFF", 5)
        seen.add((event["bid"], event["id"]))
        coordinator.replay(event)
        coordinator.replay(event)  # duplicate delivery must not duplicate the row
        print("PASS replay", event)
    with store.session() as s:
        ids = [
            r.event_id
            for r in s.scalars(
                select(OfflineRecord).where(OfflineRecord.boot_id == board.boot["bid"])
            )
        ]
        assert all(
            sum(1 for value in ids if value == event_id) == 1 for _, event_id in seen
        )
    store.engine.dispose()
    print("PASS durable replay/dedup; database directory:", Path(replay_dir).resolve())
    print(
        "Fixture test complete. Restart the backend to restore the real badge whitelist."
    )


CASES = [
    ({"t": "SYNC", "n": 0}, None),
    ({"t": "PW", "on": 1, "s": 2}, ("PW", "st", "ON")),
    ({"t": "PW", "on": 0}, ("PW", "st", "OFF")),
    ({"t": "ALARM", "on": 1, "why": "SHELF_BREACH"}, ("ALARM", "why", "SHELF_BREACH")),
    ({"t": "ACK"}, ("ALARM_OFF", "by", "ACK")),
    ({"t": "ALARM", "on": 1, "why": "PC_CMD"}, ("ALARM", "why", "PC_CMD")),
    ({"t": "ACK"}, ("ALARM_OFF", "by", "ACK")),
]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port")
    p.add_argument("--simulate", action="store_true")
    p.add_argument(
        "--offline-fixture",
        action="store_true",
        help="REPLACES the board whitelist with two supplied test tags",
    )
    p.add_argument("--badge-uid")
    p.add_argument("--item-uid")
    p.add_argument("--replay-db-dir", default="data/hardware-replay")
    args = p.parse_args()
    board = SimulatedArduino() if args.simulate else connect(args.port)
    try:
        for message, expected in CASES:
            if args.simulate:
                board.drain()
                board.receive(message)
                events = board.drain()
                if expected:
                    assert any(
                        e["t"] == expected[0] and e.get(expected[1]) == expected[2]
                        for e in events
                    ), events
            else:
                board.write(encode(message))
                if expected:
                    wait_for(
                        board,
                        lambda e: e["t"] == expected[0]
                        and e.get(expected[1]) == expected[2],
                    )
            print("PASS", message, expected or "")
        if not args.simulate:
            uid = None
            for result, n in [
                ("IN", 1),
                ("OUT", 0),
                ("DEN", 0),
                ("PRM", 0),
                ("NSS", 0),
            ]:
                print(
                    f"Tap/remove the same card for result {result}; allow >1.5 s between taps"
                )
                scan = wait_for(board, lambda e: e["t"] == "SCAN", 20)
                if uid:
                    assert scan["uid"] == uid, "Use the same test card"
                uid = scan["uid"]
                board.write(
                    encode({"t": "AUTH", "seq": scan["seq"], "r": result, "n": n})
                )
                fb = wait_for(
                    board,
                    lambda e: e["t"] == "FB" and e["seq"] == scan["seq"],
                    heartbeat=False,
                )
                assert fb["r"] == result
                print("PASS feedback", fb)
            print(
                "Dead-man test: no heartbeat is sent for the next 8 s; expect local DEADMAN alarm."
            )
            board.write(encode({"t": "PW", "on": 1, "s": 8}))
            wait_for(
                board,
                lambda e: e["t"] == "ALARM" and e["why"] == "DEADMAN",
                10,
                heartbeat=False,
            )
            print("PASS dead-man escalation without PC heartbeats")
            board.write(encode({"t": "ACK"}))
            if args.offline_fixture:
                if not args.badge_uid or not args.item_uid:
                    raise ValueError(
                        "--offline-fixture requires --badge-uid and --item-uid"
                    )
                offline_fixture(
                    board, args.badge_uid, args.item_uid, args.replay_db_dir
                )
    finally:
        if not args.simulate:
            board.write(encode({"t": "ACK"}))
            board.close()


if __name__ == "__main__":
    main()
