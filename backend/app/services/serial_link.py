"""Independent serial reader/writer; callbacks must enqueue work, never do camera I/O."""

import logging
import queue
import threading
import time
from typing import Protocol
import serial
from serial.tools import list_ports
from app.services.protocol import encode, parse
from app.sim.arduino import SimulatedArduino

log = logging.getLogger(__name__)


class Transport(Protocol):
    def read(self) -> bytes: ...
    def write(self, data: bytes) -> None: ...
    def close(self) -> None: ...


class RealSerial:
    def __init__(self, config):
        port = config.serial_port
        if not port:
            ports = [
                p.device
                for p in list_ports.comports()
                if p.vid in {0x2341, 0x1A86, 0x2A03, 0x0403}
            ]
            if len(ports) != 1:
                raise OSError("Set SERIAL_PORT: no unique Arduino USB port")
            port = ports[0]
        self.port = serial.Serial(
            port, config.serial_baud, timeout=0.1, write_timeout=0.2
        )
        self.dropping = False
        self.buffer = bytearray()

    def read(self) -> bytes:
        raw = self.port.read_until(b"\n", 98)
        if self.dropping:
            if raw.endswith(b"\n"):
                self.dropping = False
            return b""
        self.buffer.extend(raw)
        if len(self.buffer) > 97 and not self.buffer.endswith(b"\n"):
            self.dropping = True
            self.buffer.clear()
            return b"x" * 97 + b"\n"
        if self.buffer.endswith(b"\n"):
            result = bytes(self.buffer)
            self.buffer.clear()
            return result
        return b""

    def write(self, data):
        print("SERIAL WRITE:", repr(data))
        self.port.write(data)
        self.port.flush()
        
    def close(self) -> None:
        self.port.close()


class SimTransport:
    def __init__(self, board: SimulatedArduino, persist=lambda snapshot: None):
        self.board, self.lock = board, threading.RLock()
        self.persist = persist

    def read(self) -> bytes:
        with self.lock:
            self.board.tick()
            if self.board.events:
                return encode(self.board.events.popleft())
        time.sleep(0.01)
        return b""

    def write(self, data: bytes) -> None:
        with self.lock:
            before = bytes(self.board.eeprom)
            self.board.receive(parse(data))
            if self.board.eeprom != before:
                self.persist(bytes(self.board.eeprom))

    def close(self) -> None:
        pass


class SerialLink:
    def __init__(self, config, callback, simulate=False):
        self.c, self.callback, self.simulate = config, callback, simulate
        self.eeprom_queue = queue.Queue(maxsize=1)
        self.eeprom_stop = threading.Event()
        self.eeprom_thread = None
        self.eeprom_path = config.data_dir / "sim-eeprom.bin"
        image = None
        if simulate and self.eeprom_path.exists():
            raw = self.eeprom_path.read_bytes()
            if len(raw) != 1024:
                raise ValueError(
                    "Invalid simulated EEPROM image length; back up and inspect sim-eeprom.bin"
                )
            image = bytearray(raw)
        self.board = (
            SimulatedArduino(config.model_copy(deep=True), eeprom=image, readers=2)
            if simulate
            else None
        )
        if self.board:
            self.queue_eeprom(bytes(self.board.eeprom))
        self.transport = None
        self.tx = queue.Queue(maxsize=256)
        self.stop = threading.Event()
        self.connected = False
        self.last_rx = 0.0
        self.malformed = 0
        self.threads = []
        self.on_connect = lambda: None
        self.sim_disconnected = False
        self.firmware = None
        self.firmware_error = None
        self.telemetry = {}
        self.prewarn = False
        self.session_count = lambda: 0

    def send(self, m: dict) -> None:
        try:
            self.tx.put_nowait(encode(m))
        except queue.Full:
            log.error("Serial output queue full")

    def start(self) -> None:
        for target in (
            self.reader,
            self.writer,
            *((self.eeprom_writer,) if self.simulate else ()),
        ):
            t = threading.Thread(target=target, daemon=True)
            self.threads.append(t)
            if target == self.eeprom_writer:
                self.eeprom_thread = t
            t.start()

    def reader(self) -> None:
        while not self.stop.is_set():
            try:
                if not self.transport:
                    self.transport = (
                        SimTransport(self.board, self.queue_eeprom)
                        if self.simulate
                        else RealSerial(self.c)
                    )
                    self.connected = True
                    self.on_connect()
                if self.sim_disconnected:
                    if self.board:
                        with self.transport.lock:
                            self.board.tick()
                            self.board.events.clear()  # UART output is lost while disconnected; OFF ring is retained.
                    self.stop.wait(0.1)
                    continue
                raw = self.transport.read()
                if raw:
                    try:
                        m = parse(raw)
                    except ValueError:
                        self.malformed += 1
                        continue
                    if m["t"] == "HB":
                        self.last_rx = time.monotonic()
                        self.telemetry = m.copy()
                    if m["t"] == "BOOT":
                        self.firmware = m.copy()
                        self.firmware_error = (
                            None
                            if tuple(map(int, m["fw"].split(".")))
                            >= (
                                (2, 0)
                                if self.c.removal_policy == "session_lenient"
                                else (2, 1)
                            )
                            else "Firmware 2.1 required. Flash current D4/D5 build before using this app."
                        )
                    if m["t"] == "PW":
                        self.prewarn = m["st"] == "ON"
                    if m["t"] in {"ALARM", "ALARM_OFF"}:
                        self.prewarn = False
                    self.callback(m)
            except Exception:
                log.exception("Serial disconnected; retrying")
                self.connected = False
                if self.transport:
                    self.transport.close()
                self.transport = None
                self.stop.wait(1)

    def writer(self) -> None:
        next_hb = 0
        while not self.stop.is_set():
            try:
                if time.monotonic() >= next_hb:
                    self.send({"t": "HB", "n": self.session_count()})
                    next_hb = time.monotonic() + self.c.heartbeat_s
                data = self.tx.get(timeout=0.1)
                if self.transport and not self.sim_disconnected:
                    self.transport.write(data)
            except queue.Empty:
                pass
            except Exception:
                log.exception("Serial write failed")

    def queue_eeprom(self, snapshot: bytes) -> None:
        try:
            self.eeprom_queue.put_nowait(snapshot)
        except queue.Full:
            try:
                self.eeprom_queue.get_nowait()
                self.eeprom_queue.task_done()
            except queue.Empty:
                pass
            self.eeprom_queue.put_nowait(snapshot)

    def eeprom_writer(self) -> None:
        # Simulation-only persistence never blocks serial AUTH or board timer threads.
        while not self.eeprom_stop.is_set() or not self.eeprom_queue.empty():
            try:
                snapshot = self.eeprom_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self.eeprom_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.eeprom_path.with_suffix(".tmp")
                temporary.write_bytes(snapshot)
                temporary.replace(self.eeprom_path)
            except OSError:
                log.exception("Simulated EEPROM persistence failed")
            finally:
                self.eeprom_queue.task_done()

    def close(self) -> None:
        self.stop.set()
        for t in self.threads:
            if t is not self.eeprom_thread:
                t.join(2)
        self.eeprom_stop.set()
        if self.eeprom_thread:
            self.eeprom_thread.join(2)
        if self.transport:
            self.transport.close()
