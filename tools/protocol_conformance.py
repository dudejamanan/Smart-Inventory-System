"""v2 command conformance. Real board mode needs main sketch and physical card taps."""

import argparse
from common import connect, wait_for, encode
from app.sim.arduino import SimulatedArduino

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
    finally:
        if not args.simulate:
            board.write(encode({"t": "ACK"}))
            board.close()


if __name__ == "__main__":
    main()
