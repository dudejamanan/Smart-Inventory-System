from app.services.serial_link import RealSerial


class Port:
    def __init__(self, parts):
        self.parts = iter(parts)

    def read_until(self, *args):
        return next(self.parts)


def transport(parts):
    link = RealSerial.__new__(RealSerial)
    link.port = Port(parts)
    link.dropping = False
    link.buffer = bytearray()
    return link


def test_partial_serial_and_drop_overflow():
    link = transport([b'{"t":', b'"HB"}', b"\n"])
    assert link.read() == b"" and link.read() == b""
    assert link.read() == b'{"t":"HB"}\n'
    link = transport([b"x" * 98, b"junk\n", b'{"t":"HB"}\n'])
    assert len(link.read().strip()) == 97
    assert link.read() == b""
    assert link.read() == b'{"t":"HB"}\n'
