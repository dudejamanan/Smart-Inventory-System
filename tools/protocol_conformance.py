"""v2 command conformance. Real board mode needs main sketch and physical card taps."""

import argparse
import time
from pathlib import Path

from common import connect, wait_for, encode
from app.sim.arduino import SimulatedArduino
from app.services.protocol import fnv1a, whitelist_messages


def offline_fixture(board, badge, item, replay_dir="data/hardware-replay"):
    """Explicit destructive test fixture; backend replaces it on next normal sync."""
    if badge == item:
        raise ValueError("Badge and item must be different tags")

    board.write(encode({"t": "HB", "n": 0}))

    for message in whitelist_messages(
        [(fnv1a(badge), 2, False), (fnv1a(item), 1, True)]
    ):
        board.write(encode(message))
        time.sleep(0.04)

    assert wait_for(board, lambda e: e["t"] == "WLOK")["n"] == 2
    print("PASS EEPROM upload count/CRC. No heartbeats now; keep USB connected.")

    wait_for(
        board,
        lambda e: e["t"] == "HB" and e["pcok"] == 0,
        seconds=10,
        heartbeat=False,
    )

    for uid, result in [(badge, "IN"), (item, "ISS"), (badge, "OUT")]:
        reader = 2 if uid == item else 1
        print(
            f"Offline: tap {uid} on reader #{reader} for {result}; "
            "remove cards between taps."
        )

        scan = wait_for(
            board, lambda e: e["t"] == "SCAN", seconds=25, heartbeat=False
        )
        assert scan["uid"] == uid, f"Expected {uid}, saw {scan['uid']}"

        fb = wait_for(
            board,
            lambda e: e["t"] == "FB" and e["seq"] == scan["seq"],
            heartbeat=False,
        )
        assert fb["r"] == result, fb
        print("PASS offline", result, fb)

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
        event = wait_for(board, lambda e: e["t"] == "OFF", seconds=5)
        seen.add((event["bid"], event["id"]))
        coordinator.replay(event)
        coordinator.replay(event)
        print("PASS replay", event)

    with store.session() as session:
        ids = [
            record.event_id
            for record in session.scalars(
                select(OfflineRecord).where(
                    OfflineRecord.boot_id == board.boot["bid"]
                )
            )
        ]

        assert all(
            sum(1 for value in ids if value == event_id) == 1
            for _, event_id in seen
        )

    store.engine.dispose()
    print(
        "PASS durable replay/dedup; database directory:",
        Path(replay_dir).resolve(),
    )
    print(
        "Fixture test complete. Restart the backend to restore "
        "the real badge whitelist."
    )


CASES = [
    ({"t": "SYNC", "n": 0}, None),
    ({"t": "PW", "on": 1, "s": 10}, ("PW", "st", "ON")),
    ({"t": "PW", "on": 0}, ("PW", "st", "OFF")),
    (
        {"t": "ALARM", "on": 1, "why": "SHELF_BREACH"},
        ("ALARM", "why", "SHELF_BREACH"),
    ),
    ({"t": "ACK"}, ("ALARM_OFF", "by", "ACK")),
    (
        {"t": "ALARM", "on": 1, "why": "PC_CMD"},
        ("ALARM", "why", "PC_CMD"),
    ),
    ({"t": "ACK"}, ("ALARM_OFF", "by", "ACK")),
]


def run_deadman_test(board):
    """Verify pulse expiry and DEADMAN alarm without PC heartbeats."""
    print(
        "\nDead-man test: remove cards from both readers. "
        "The PC will stop sending heartbeats."
    )

    # Clear any previous alarm.
    board.write(encode({"t": "ACK"}))
    try:
        event = wait_for(
            board,
            lambda e: e.get("t") == "ALARM_OFF" and e.get("by") == "ACK",
            seconds=3,
        )
        print("PASS pre-test alarm clear:", event)
    except TimeoutError:
        print("INFO no prior alarm acknowledgement; continuing")

    # Start a 10-second local pulse.
    board.write(encode({"t": "PW", "on": 1, "s": 10}))
    event = wait_for(
        board,
        lambda e: e.get("t") == "PW" and e.get("st") == "ON",
        seconds=3,
    )
    print("PASS pulse active:", event)
    print("INFO withholding PC heartbeats; waiting up to 14 seconds")

    deadline = time.monotonic() + 14
    pc_off_seen = False
    pulse_expired = False
    deadman_alarm = None

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        try:
            event = wait_for(
                board,
                lambda e: (
                    e.get("t") == "PW"
                    and e.get("st") == "ESC"
                )
                or (
                    e.get("t") == "ALARM"
                )
                or (
                    e.get("t") == "HB"
                    and e.get("pcok") == 0
                ),
                seconds=min(2, max(0.1, remaining)),
                heartbeat=False,
            )
        except TimeoutError:
            print("INFO no matching watchdog event in this interval")
            continue

        print("DEADMAN RX:", event)

        if event.get("t") == "HB" and event.get("pcok") == 0:
            if not pc_off_seen:
                print("PASS PC-presence watchdog reports pcok=0")
            pc_off_seen = True

        elif event.get("t") == "PW" and event.get("st") == "ESC":
            pulse_expired = True
            print("PASS local pulse expired: PW ESC")

        elif event.get("t") == "ALARM":
            if event.get("why") == "DEADMAN":
                deadman_alarm = event
                print("PASS DEADMAN alarm:", event)
                break

            print("WARNING other alarm observed:", event)

    if not pulse_expired:
        print("FAIL no PW ESC event observed")
    if not deadman_alarm:
        print("FAIL expected ALARM DEADMAN was not observed")
    if not pc_off_seen:
        print("WARNING no HB with pcok=0 observed")

    if not pulse_expired or not deadman_alarm:
        print(
            "Dead-man test FAILED. Do not treat PC disconnection "
            "alone as proof of pulse-expiry alarm behavior."
        )
        return False

    # Restore PC presence, then acknowledge the alarm.
    board.write(encode({"t": "HB", "n": 0}))

    try:
        event = wait_for(
            board,
            lambda e: e.get("t") == "HB" and e.get("pcok") == 1,
            seconds=4,
            heartbeat=False,
        )
        print("PASS PC presence restored:", event)
    except TimeoutError:
        print("WARNING PC presence did not return to pcok=1")

    board.write(encode({"t": "ACK"}))

    try:
        event = wait_for(
            board,
            lambda e: (
                e.get("t") == "ALARM_OFF"
                and e.get("by") == "ACK"
            ),
            seconds=4,
        )
        print("PASS DEADMAN alarm acknowledged:", event)
    except TimeoutError:
        print("FAIL DEADMAN alarm acknowledgement timed out")
        return False

    return True



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument(
        "--offline-fixture",
        action="store_true",
        help="REPLACES the board whitelist with two supplied test tags",
    )
    parser.add_argument("--badge-uid")
    parser.add_argument("--item-uid")
    parser.add_argument("--replay-db-dir", default="data/hardware-replay")
    args = parser.parse_args()

    board = SimulatedArduino() if args.simulate else connect(args.port)

    try:
        for message, expected in CASES:
            if args.simulate:
                board.drain()
                board.receive(message)
                events = board.drain()

                if expected:
                    assert any(
                        event["t"] == expected[0]
                        and event.get(expected[1]) == expected[2]
                        for event in events
                    ), events
            else:
                encoded = encode(message)
                print("DEBUG TX:", encoded.decode(errors="replace").strip())
                board.write(encoded)

                if expected:
                    wait_for(
                        board,
                        lambda event: event["t"] == expected[0]
                        and event.get(expected[1]) == expected[2],
                        seconds=5,
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
                    f"Tap/remove the same card for result {result}; "
                    "allow >1.5 s between taps."
                )

                scan = wait_for(
                    board, lambda event: event["t"] == "SCAN", seconds=20
                )

                if uid:
                    assert scan["uid"] == uid, "Use the same test card"

                uid = scan["uid"]

                board.write(
                    encode(
                        {
                            "t": "AUTH",
                            "seq": scan["seq"],
                            "r": result,
                            "n": n,
                        }
                    )
                )

                fb = wait_for(
                    board,
                    lambda event: event["t"] == "FB"
                    and event["seq"] == scan["seq"],
                    seconds=5,
                    heartbeat=False,
                )

                assert fb["r"] == result, fb
                print("PASS feedback", fb)

            # Keep the card away from both readers during this phase.
            if not run_deadman_test(board):
                raise SystemExit(1)

            if args.offline_fixture:
                if not args.badge_uid or not args.item_uid:
                    raise ValueError(
                        "--offline-fixture requires --badge-uid and --item-uid"
                    )

                offline_fixture(
                    board,
                    args.badge_uid,
                    args.item_uid,
                    args.replay_db_dir,
                )

    finally:
        if not args.simulate:
            board.close()


if __name__ == "__main__":
    main()
