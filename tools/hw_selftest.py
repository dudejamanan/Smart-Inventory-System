"""Interactive electrical test: no PASS without a human observation."""

import argparse
import threading
from common import connect, wait_for, encode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port")
    parser.add_argument("--readers", type=int, choices=[1, 2], default=2)
    parser.add_argument(
        "--button",
        action="store_true",
        help="Only if optional A0 button is wired and BUTTON_ENABLED=1",
    )
    parser.add_argument(
        "--offline-fixture",
        action="store_true",
        help="Explicitly replace cache and test two physical tags",
    )
    parser.add_argument("--badge-uid")
    parser.add_argument("--item-uid")
    args = parser.parse_args()
    board = connect(args.port)
    stopped = threading.Event()
    write_lock = threading.Lock()

    def write(message):
        with write_lock:
            board.write(encode(message))

    def keepalive():
        while not stopped.is_set():
            try:
                write({"t": "HB", "n": 0})
            except OSError:
                return
            stopped.wait(2)

    heartbeat = threading.Thread(target=keepalive, daemon=True)
    heartbeat.start()
    passed = True
    try:
        print("BOOT:", board.boot)
        if board.boot["rd"] != args.readers:
            raise ValueError("READER_COUNT does not match --readers")
        for what in ["green", "red", "buzzer"]:
            write({"t": "TEST", "what": what})
            answer = (
                input(f"Did {what} turn on for about 1 second? [y/N] ").strip().lower()
            )
            ok = answer == "y"
            passed &= ok
            print(f"{what}: " + ("PASS (observed by operator)" if ok else "FAIL"))
        print("Tap a card within 20 seconds. It will be denied during this test.")
        event = wait_for(board, lambda e: e["t"] == "SCAN", 20, heartbeat=False)
        print("UID:", event["uid"])
        write({"t": "AUTH", "seq": event["seq"], "r": "DEN", "n": 0})
        wait_for(board, lambda e: e["t"] == "FAIL", heartbeat=False)
        print("Serial scan and denial exchange: PASS")
        if args.readers == 2:
            print("Now tap a tag on reader 1 within 20 s.")
            event = wait_for(board, lambda e: e["t"] == "SCAN", 20, heartbeat=False)
            assert event["rd"] == 1, "Tag was read by the wrong reader"
            write({"t": "AUTH", "seq": event["seq"], "r": "DEN", "n": 0})
            print("Reader 1 scan: PASS")
        if args.button:
            print(
                "Press/release A0 briefly, then hold >=1.5 s and release (20 s each)."
            )
        else:
            print("Button: SKIPPED (not present in supplied circuit)")
        for kind in ["S", "L"] if args.button else []:
            wait_for(
                board, lambda e: e["t"] == "BTN" and e["k"] == kind, 20, heartbeat=False
            )
            print("Button", kind, ": PASS")
        telemetry = wait_for(board, lambda e: e["t"] == "HB", 5, heartbeat=False)
        print("Board telemetry (actual reported values):", telemetry)
        assert 0 < telemetry["ram"] <= 2048
        if args.offline_fixture:
            if not args.badge_uid or not args.item_uid:
                raise ValueError("Supply --badge-uid and --item-uid")
            stopped.set()
            heartbeat.join(2)
            from protocol_conformance import offline_fixture

            offline_fixture(board, args.badge_uid, args.item_uid)
    except Exception as exc:
        passed = False
        print("FAIL:", exc)
    finally:
        stopped.set()
        heartbeat.join(2)
        write({"t": "ACK"})
        board.close()
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
