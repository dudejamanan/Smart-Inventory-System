"""Configuration is loaded from the repository .env, never from source secrets."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

ROOT = Path(__file__).resolve().parents[2]

class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    data_dir: Path = ROOT / 'data'
    admin_password: str = ''
    cookie_secret: str = ''
    media_url_secret: str = ''
    cookie_secure: bool = False
    serial_port: str = ''
    serial_baud: int = 115200
    fail_limit: int = Field(3, ge=1, le=20)
    fail_window_s: int = Field(60, ge=1, le=3600)
    alarm_s: int = Field(30, ge=1, le=3600)
    heartbeat_s: float = 2
    pc_lost_s: float = 6
    auth_timeout_ms: int = 1000
    process_fps: int = 10
    debounce_n: int = 4
    debounce_m: int = 5
    occluded_warn_s: float = 2
    empty_diff_thresh: float = 12
    cam_offline_s: float = 3
    covered_brightness: float = 15
    covered_variance: float = 5
    anchor_tolerance: float = .04
    retention_days: int = 30
    log_valid_scan_photos: bool = True
    gate_camera_index: int = 0
    shelf_stream_url: str = ''
    shelf_video_file: str = ''
    whatsapp_on: str = 'third_failure'
    zones_enabled: bool = False
    twilio_account_sid: str = ''
    twilio_auth_token: str = ''
    twilio_whatsapp_from: str = ''
    owner_whatsapp_to: str = ''
    public_base_url: str = ''

    @property
    def db_url(self) -> str:
        return 'sqlite:///' + (self.data_dir / 'warehouse.db').as_posix()
