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
            ports = [p.device for p in list_ports.comports() if p.vid in {0x2341,0x1A86,0x2A03,0x0403}]
            if len(ports) != 1:
                raise OSError('Set SERIAL_PORT: no unique Arduino USB port')
            port = ports[0]
        self.port = serial.Serial(port, config.serial_baud, timeout=.1, write_timeout=.2)
        self.dropping = False

    def read(self) -> bytes:
        raw = self.port.read_until(b'\n', 98)
        if self.dropping:
            if raw.endswith(b'\n'):
                self.dropping = False
            return b''
        if len(raw) >= 98 and not raw.endswith(b'\n'):
            self.dropping = True
        return raw

    def write(self, data: bytes) -> None:
        self.port.write(data)

    def close(self) -> None:
        self.port.close()

class SimTransport:
    def __init__(self, board: SimulatedArduino):
        self.board, self.lock = board, threading.RLock()

    def read(self) -> bytes:
        with self.lock:
            self.board.tick()
            if self.board.events:
                return encode(self.board.events.popleft())
        time.sleep(.01)
        return b''

    def write(self, data: bytes) -> None:
        with self.lock:
            self.board.receive(parse(data))

    def close(self) -> None:
        pass

class SerialLink:
    def __init__(self, config, callback, simulate=False):
        self.c, self.callback, self.simulate = config, callback, simulate
        self.board = SimulatedArduino(config.model_copy(deep=True)) if simulate else None
        self.transport = None
        self.tx = queue.Queue(maxsize=256)
        self.stop = threading.Event()
        self.connected = False
        self.last_rx = 0.0
        self.malformed = 0
        self.threads = []
        self.on_connect = lambda: None
        self.sim_disconnected = False

    def send(self, m: dict) -> None:
        try:
            self.tx.put_nowait(encode(m))
        except queue.Full:
            log.error('Serial output queue full')

    def start(self) -> None:
        for target in (self.reader, self.writer):
            t = threading.Thread(target=target, daemon=True)
            self.threads.append(t)
            t.start()

    def reader(self) -> None:
        while not self.stop.is_set():
            try:
                if not self.transport:
                    self.transport = SimTransport(self.board) if self.simulate else RealSerial(self.c)
                    self.connected = True
                    self.on_connect()
                if self.sim_disconnected:
                    self.stop.wait(.1)
                    continue
                raw = self.transport.read()
                if raw:
                    try:
                        m = parse(raw)
                    except ValueError:
                        self.malformed += 1
                        continue
                    if m['t'] == 'HB':
                        self.last_rx = time.monotonic()
                    self.callback(m)
            except Exception:
                log.exception('Serial disconnected; retrying')
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
                    self.send({'t':'HB'})
                    next_hb = time.monotonic()+self.c.heartbeat_s
                data = self.tx.get(timeout=.1)
                if self.transport and not self.sim_disconnected:
                    self.transport.write(data)
            except queue.Empty:
                pass
            except Exception:
                log.exception('Serial write failed')

    def close(self) -> None:
        self.stop.set()
        for t in self.threads:
            t.join(2)
        if self.transport:
            self.transport.close()
