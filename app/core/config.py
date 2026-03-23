from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Darkweb Monitor"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_key: str = "change-me"

    database_url: str = "postgresql://intel:intelpass@127.0.0.1:5432/intel"

    user_agent: str = "DarkwebMonitor/2.0"
    request_timeout_seconds: float = 20.0
    poll_interval_seconds: int = 10
    worker_count: int = 4
    max_depth: int = 2
    max_pages_per_host: int = 100
    revisit_after_seconds: int = 300
    alert_cooldown_seconds: int = 3600

    targets_seed_path: Path = BASE_DIR / "targets.json"
    watchlist_seed_path: Path = BASE_DIR / "watchlist.json"
    evidence_dir: Path = BASE_DIR / "evidence"
    html_dir: Path = BASE_DIR / "evidence" / "html"
    text_dir: Path = BASE_DIR / "evidence" / "text"
    screenshot_dir: Path = BASE_DIR / "evidence" / "screenshots"
    ui_dir: Path = BASE_DIR / "ui"

    discord_webhook_url: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    screenshot_enabled: bool = True
    playwright_timeout_ms: int = 15000


settings = Settings()
