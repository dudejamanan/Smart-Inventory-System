import pytest
from sqlalchemy import select
from app.sim.arduino import SimulatedArduino
from app.services.protocol import fnv1a, whitelist_messages, crc16
from app.services.offline import OfflineCoordinator
from app.db.models import OfflineRecord, SecurityEvent
from app.db.store import Store
from app.config import Config
from test_v2_board import Clock

BADGE = "A1B2C3D4"
OTHER = "11223344"
ITEM = "00112233"
HIGH = "44556677"


def install(board, entries):
    for message in whitelist_messages(entries):
        board.receive(message)
    assert board.drain()[-1] == {"t": "WLOK", "n": len(entries)}


def configured():
    c = Clock()
    b = SimulatedArduino(clock=c)
    entries = [
        (fnv1a(BADGE), 2, False),
        (fnv1a(OTHER), 1, False),
        (fnv1a(ITEM), 1, True),
        (fnv1a(HIGH), 3, True),
    ]
    install(b, entries)
    return b, c, entries


def scan(b, c, uid):
    c.advance(1.6)
    b.scan(uid)
    return b.drain()


def test_staging_crc_preserves_eeprom_until_valid_end():
    b, c, entries = configured()
    before = bytes(b.eeprom)
    messages = whitelist_messages([(fnv1a(OTHER), 3, False)])
    for m in messages[:-1]:
        b.receive(m)
    assert bytes(b.eeprom) == before
    b.receive(messages[-1] | {"ck": messages[-1]["ck"] ^ 1})
    assert b.drain()[-1]["why"] == "CRC" and bytes(b.eeprom) == before
    install(b, entries)
    reboot = SimulatedArduino(clock=c, eeprom=b.eeprom)
    assert (
        reboot.boot_id == b.boot_id + 1
        and reboot.whitelist == entries
        and not reboot.logs
    )
    reboot.eeprom[8] ^= 1
    assert SimulatedArduino(clock=c, eeprom=reboot.eeprom).whitelist == []


def test_capacity_duplicates_and_offline_staging_abort():
    c = Clock()
    b = SimulatedArduino(clock=c)
    entries = [(i, 1, False) for i in range(100)]
    install(b, entries)
    assert len(b.whitelist) == 100
    with pytest.raises(ValueError):
        whitelist_messages(entries + [(101, 1, False)])
    original = bytes(b.eeprom)
    b.receive({"t": "WL", "op": "CLR", "n": 2})
    for _ in range(2):
        b.receive({"t": "WL", "op": "ADD", "h": "00000001", "lv": 1, "it": 0})
    assert b.drain()[-1]["why"] == "DUP" and bytes(b.eeprom) == original
    b.receive({"t": "WL", "op": "CLR", "n": 0})
    c.advance(7)
    b.tick()
    b.receive({"t": "WL", "op": "END", "n": 0, "ck": crc16(bytes([2, 0]))})
    assert b.drain()[-1]["why"] == "STATE" and bytes(b.eeprom) == original


def test_offline_badges_items_levels_recent_and_ambiguity():
    b, c, entries = configured()
    c.advance(7)
    b.tick()
    b.drain()
    assert scan(b, c, BADGE)[-1]["r"] == "IN" and b.n == 1
    assert scan(b, c, ITEM)[-1]["r"] == "ISS"
    assert scan(b, c, HIGH)[-1]["r"] == "PRM" and b.failures == 0
    assert scan(b, c, OTHER)[-1]["r"] == "IN" and b.n == 2
    assert scan(b, c, HIGH)[-1]["r"] == "PRM"
    c.advance(31)
    assert scan(b, c, ITEM)[-1]["r"] == "NSS" and b.failures == 1
    assert scan(b, c, OTHER)[-1]["r"] == "OUT" and b.n == 1
    assert scan(b, c, ITEM)[-1]["r"] == "ISS"  # sole badge fallback
    assert scan(b, c, BADGE)[-1]["r"] == "OUT" and b.n == 0
    assert scan(b, c, ITEM)[-1]["r"] == "NSS"


def test_full_ring_denies_and_replay_requires_matching_oldest_ack():
    b, c, entries = configured()
    c.advance(7)
    for _ in range(16):
        scan(b, c, BADGE)
    assert len(b.logs) == 16
    n = b.n
    assert scan(b, c, BADGE)[-1]["r"] == "PRM" and b.n == n
    b.receive({"t": "HB", "n": 0})
    b.tick()
    first = next(e for e in b.drain() if e["t"] == "OFF")
    b.receive({"t": "OFFOK", "id": first["id"] + 1})
    assert len(b.logs) == 16
    c.advance(1)
    b.tick()
    again = next(e for e in b.drain() if e["t"] == "OFF")
    assert first["id"] == again["id"]
    b.receive({"t": "WL", "op": "CLR", "n": 0})
    assert b.drain()[-1]["why"] == "BUSY"
    b.receive({"t": "OFFOK", "id": first["id"]})
    assert len(b.logs) == 15


def test_replay_commit_dedup_and_no_ack_with_failed_database(tmp_path, monkeypatch):
    from unittest.mock import Mock

    store = Store(Config(data_dir=tmp_path))
    link = Mock()
    o = OfflineCoordinator(store, link, lambda: [])
    event = {"t": "OFF", "bid": 5, "id": 1, "h": "12345678", "e": "IN", "ago": 2}
    o.replay(event)
    o.replay(event | {"ago": 3})
    with store.session() as s:
        assert len(s.scalars(select(OfflineRecord)).all()) == 1
        assert (
            len(
                s.scalars(
                    select(SecurityEvent).where(SecurityEvent.type == "OFFLINE_EVENT")
                ).all()
            )
            == 1
        )
    assert link.send.call_count == 2
    link.reset_mock()

    def failed():
        raise OSError("DB down")

    monkeypatch.setattr(store, "session", failed)
    with pytest.raises(OSError):
        o.replay(event | {"id": 2})
    link.send.assert_not_called()
    store.engine.dispose()
