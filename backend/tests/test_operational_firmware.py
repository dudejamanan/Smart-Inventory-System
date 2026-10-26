from app.config import Config
from app.runtime import Runtime


def test_old_pin_profile_is_denied_until_current_firmware_boot(tmp_path):
    r = Runtime(
        Config(data_dir=tmp_path, twilio_account_sid="", twilio_auth_token=""),
        simulate=True,
    )
    try:
        r.on_serial(dict(t="BOOT", fw="2.0", rst="PWR", rd=2, bid=1))
        assert r.status()["serial"]["error"]
        r.on_serial(dict(t="SCAN", uid="A1B2C3D4", seq=1, rd=0))
        assert r.engine.pending_results[1]["r"] == "DEN"
        r.on_serial(dict(t="BOOT", fw="2.1", rst="PWR", rd=2, bid=2))
        assert not r.status()["serial"]["error"]
        r.on_serial(dict(t="SCAN", uid="A1B2C3D4", seq=2, rd=0))
        assert r.engine.pending_results[2]["r"] == "IN"
    finally:
        r.close()
