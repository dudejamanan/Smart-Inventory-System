"""Shared import bootstrap and real-board serial helpers."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.protocol import parse, encode
from app.config import Config
from app.services.serial_link import RealSerial


def connect(port=None):
    c = Config()
    if port:
        c.serial_port = port
    board = RealSerial(c)
    # Opening serial resets UNO. Pump until BOOT or wait two seconds.
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        raw = board.read()
        if raw:
            try:
                if parse(raw)["t"] == "BOOT":
                    break
            except ValueError:
                pass
    board.write(encode({"t": "HB"}))
    return board


def wait_for(board, predicate, seconds=5, heartbeat=True, on_event=None):
    end = time.monotonic() + seconds
    next_hb = 0
    while time.monotonic() < end:
        if heartbeat and time.monotonic() > next_hb:
            board.write(encode({"t": "HB"}))
            next_hb = time.monotonic() + 2
        raw = board.read()
        if not raw:
            continue
        try:
            event = parse(raw)
        except ValueError:
            continue
        if on_event:
            on_event(event)
        if predicate(event):
            return event
    raise TimeoutError("No matching board response; check wiring/port and try again")
