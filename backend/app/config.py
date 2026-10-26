"""Configuration is loaded from the repository .env, never from source secrets."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, model_validator

ROOT = Path(__file__).resolve().parents[2]


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    data_dir: Path = ROOT / "data"
    admin_password: str = ""
    cookie_secret: str = ""
    media_url_secret: str = ""
    cookie_secure: bool = False
    serial_port: str = ""
    board_id: str = "gate-0"
    serial_baud: int = 115200
    fail_limit: int = Field(3, ge=1, le=20)
    fail_window_s: int = Field(60, ge=1, le=3600)
    alarm_s: int = Field(30, ge=1, le=3600)
    heartbeat_s: float = Field(2, gt=0, le=5)
    pc_lost_s: float = Field(6, ge=1)
    auth_timeout_ms: int = Field(1000, ge=100, le=10000)
    process_fps: int = Field(10, ge=1, le=30)
    debounce_n: int = Field(4, ge=1, le=30)
    debounce_m: int = Field(5, ge=1, le=30)
    occluded_warn_s: float = Field(2, ge=0)
    empty_diff_thresh: float = Field(12, ge=0, le=255)
    cam_offline_s: float = Field(3, gt=0)
    covered_brightness: float = Field(15, ge=0, le=255)
    covered_variance: float = Field(5, ge=0)
    anchor_tolerance: float = Field(0.04, gt=0, le=1)
    retention_days: int = Field(30, ge=1)
    log_valid_scan_photos: bool = False
    gate_photo_policy: str = "third_failure"
    removal_policy: str = "strict_issue"
    max_sessions: int = Field(4, ge=1, le=8)
    session_ttl_min: float = Field(30, gt=0)
    attribution_window_s: float = Field(30, gt=0)
    removal_grace_s: int = Field(10, ge=1, le=60)
    issue_token_ttl_s: float = Field(30, gt=0)
    return_grace_s: float = Field(20, gt=0)
    return_place_s: float = Field(60, gt=0)
    overdue_check_s: float = Field(30, gt=0)
    slot_mode: str = "both"
    gate_camera_index: int = 0
    shelf_stream_url: str = ""
    shelf_video_file: str = ""
    whatsapp_on: str = "third_failure"
    zones_enabled: bool = False
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""
    owner_whatsapp_to: str = ""
    public_base_url: str = ""
    notify_channels: str = "whatsapp"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    @field_validator("data_dir")
    @classmethod
    def absolute_data(cls, value: Path) -> Path:
        return (ROOT / value).resolve() if not value.is_absolute() else value.resolve()

    @model_validator(mode="after")
    def consistent(self):
        if set(self.notify_channels.split(",")) - {"whatsapp", "telegram", ""}:
            raise ValueError("NOTIFY_CHANNELS supports whatsapp,telegram")
        if self.removal_policy not in {"strict_issue", "session_lenient"}:
            raise ValueError("Invalid removal policy")
        if self.gate_photo_policy not in {"third_failure", "every_scan"}:
            raise ValueError("Invalid gate photo policy")
        if self.slot_mode not in {"both", "reveal", "empty_ref"}:
            raise ValueError("Invalid slot mode")
        if self.debounce_n > self.debounce_m:
            raise ValueError("DEBOUNCE_N must not exceed DEBOUNCE_M")
        if self.whatsapp_on not in {"third_failure", "every_failure"}:
            raise ValueError("WHATSAPP_ON must be third_failure or every_failure")
        return self

    @property
    def db_url(self) -> str:
        return "sqlite:///" + (self.data_dir / "warehouse.db").as_posix()
