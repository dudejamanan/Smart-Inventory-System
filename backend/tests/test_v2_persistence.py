import threading
from app.config import Config
from app.services.serial_link import SerialLink
from app.services.protocol import fnv1a, whitelist_messages, encode


def test_simulated_eeprom_and_boot_id_survive_backend_restart(tmp_path):
    c = Config(data_dir=tmp_path)
    ready = threading.Event()
    link = SerialLink(
        c, lambda m: ready.set() if m["t"] == "BOOT" else None, simulate=True
    )
    link.start()
    try:
        assert ready.wait(2)
        entries = [(fnv1a("A1B2C3D4"), 2, False)]
        for m in whitelist_messages(entries):
            link.transport.write(encode(m))
        link.eeprom_queue.join()
        boot = link.board.boot_id
    finally:
        link.close()
    other = SerialLink(c, lambda m: None, simulate=True)
    other.start()
    try:
        other.eeprom_queue.join()
        assert other.board.boot_id == boot + 1 and other.board.whitelist == entries
    finally:
        other.close()
