"""Interactive electrical test: no PASS without a human observation."""

import argparse
import threading
from common import connect, wait_for, encode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port")
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
                write({"t": "HB"})
            except OSError:
                return
            stopped.wait(2)

    heartbeat = threading.Thread(target=keepalive, daemon=True)
    heartbeat.start()
    passed = True
    try:
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
        write({"t": "AUTH", "seq": event["seq"], "ok": 0})
        wait_for(board, lambda e: e["t"] == "FAIL", heartbeat=False)
        print("Serial scan and denial exchange: PASS")
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
