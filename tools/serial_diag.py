import time
import serial

PORT = "COM11"
BAUD = 115200

with serial.Serial(PORT, BAUD, timeout=0.2) as s:
    print("Connected. Waiting for board boot...")
    time.sleep(2)
    while s.in_waiting:
        print("RX:", repr(s.readline()))

    for command in (
        b'{"t":"SYNC","n":0}\n',
        b'{"t":"PW","on":1,"s":10}\n',
        b'{"t":"PW","on":0}\n',
    ):
        print("TX:", command.decode().strip())
        s.write(command)
        s.flush()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            line = s.readline()
            if line:
                print("RX:", line.decode(errors="replace").strip())
