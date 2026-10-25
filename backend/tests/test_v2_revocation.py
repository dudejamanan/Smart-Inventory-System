from app.services.protocol import fnv1a
from test_v2_offline import configured, scan, install, BADGE, ITEM


def test_committed_cache_revokes_or_downgrades_remembered_badges():
    b, c, _ = configured()
    c.advance(7)
    assert scan(b, c, BADGE)[-1]["r"] == "IN"
    b.receive({"t": "HB", "n": 0})
    while b.logs:
        b.receive({"t": "OFFOK", "id": b.logs[0]["id"]})
    install(b, [(fnv1a(BADGE), 1, False), (fnv1a(ITEM), 2, True)])
    c.advance(7)
    assert scan(b, c, ITEM)[-1]["r"] == "PRM"
    b.receive({"t": "HB", "n": 0})
    while b.logs:
        b.receive({"t": "OFFOK", "id": b.logs[0]["id"]})
    install(b, [(fnv1a(ITEM), 2, True)])
    c.advance(7)
    assert scan(b, c, ITEM)[-1]["r"] == "NSS"
