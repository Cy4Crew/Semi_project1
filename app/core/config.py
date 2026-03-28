from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    app_name: str = "Darkweb Monitor"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_key: str = "change-me"

    # Docker 기준
    database_url: str = "postgresql://intel:intelpass@db:5432/intel"

    user_agent: str = "DarkwebMonitor/2.0"
    request_timeout_seconds: float = 60.0
    poll_interval_seconds: int = 5
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

    ransomware_live_api_base_url: str = "https://api.ransomware.live/v2"

    discord_webhook_url: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    screenshot_enabled: bool = True
    playwright_timeout_ms: int = 30000

    # Tor 설정 (Docker 기준)
    tor_enabled: bool = True
    tor_socks_host: str = "tor"
    tor_socks_port: int = 9050
    tor_for_all_requests: bool = False

    @property
    def tor_proxy_url(self) -> str:
        # 핵심: socks5h 사용
        return f"socks5h://{self.tor_socks_host}:{self.tor_socks_port}"


settings = Settings()