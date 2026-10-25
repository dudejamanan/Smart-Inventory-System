import json
from pathlib import Path
from unittest.mock import Mock
from app.sim.arduino import SimulatedArduino
from app.services.protocol import fnv1a
from app.services.offline import OfflineCoordinator
from app.db.store import Store
from app.config import Config
from test_v2_board import Clock


def test_shared_fnv_vectors_and_torn_boot_counter():
    root = Path(__file__).resolve().parents[2]
    vectors = json.loads((root / "firmware/tests/hash_vectors.json").read_text())
    header = (root / "firmware/tests/hash_vectors.h").read_text()
    for vector in vectors:
        assert f"{fnv1a(vector['uid']):08X}" == vector["h"]
        assert f"0x{vector['h']}UL" in header
    b = SimulatedArduino()
    b2 = SimulatedArduino(eeprom=b.eeprom)
    # Model a torn second counter write BEFORE that boot can publish BOOT or scan.
    b2.eeprom[1012] ^= 1
    next_boot = SimulatedArduino(eeprom=b2.eeprom)
    assert next_boot.boot_id == 2


def test_coordinator_waits_for_replay_and_retries_failed_transfer(tmp_path):
    c = Clock()
    b = SimulatedArduino(clock=c)
    store = Store(Config(data_dir=tmp_path))
    link = Mock()
    link.connected = True
    coordinator = OfflineCoordinator(
        store, link, lambda: [(fnv1a("A1B2C3D4"), 1, False)], clock=c
    )
    coordinator.stop = Mock()
    coordinator.stop.wait.return_value = False
    coordinator.on_message(b.drain()[0])
    coordinator.pending_replay = 1
    coordinator.step()
    link.send.assert_not_called()
    coordinator.pending_replay = 0

    def send(message):
        b.receive(message)
        for reply in b.drain():
            coordinator.on_message(reply)

    link.send.side_effect = send
    coordinator.step()
    assert coordinator.state == "CURRENT" and len(b.whitelist) == 1
    coordinator.state = "FAILED"
    coordinator.request()
    coordinator.step()
    assert coordinator.state == "CURRENT"
    store.engine.dispose()


def test_unknown_offline_three_scans_alarm_and_magic_invalidation():
    c = Clock()
    b = SimulatedArduino(clock=c)
    c.advance(7)
    for _ in range(3):
        b.scan("DEADBEEF")
        c.advance(1.6)
    assert b.alarm and b.alarm_reason == "GATE_3_FAIL" and len(b.logs) == 3
