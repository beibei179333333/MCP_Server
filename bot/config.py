"""集中化配置。从 .env 读取，提供类型安全的访问。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _split_ids(raw: str) -> List[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


@dataclass
class Settings:
    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    api_id: int = field(default_factory=lambda: int(os.getenv("TG_API_ID", "0") or 0))
    api_hash: str = field(default_factory=lambda: os.getenv("TG_API_HASH", ""))
    phone: str = field(default_factory=lambda: os.getenv("TG_PHONE", ""))
    admin_ids: List[int] = field(
        default_factory=lambda: _split_ids(os.getenv("ADMIN_IDS", ""))
    )
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", "sqlite+aiosqlite:///./bot.db"
        )
    )
    timezone: str = field(default_factory=lambda: os.getenv("TIMEZONE", "Asia/Shanghai"))
    broadcast_interval_ms: int = field(
        default_factory=lambda: int(os.getenv("BROADCAST_INTERVAL_MS", "80"))
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    session_path: Path = field(default_factory=lambda: BASE_DIR / "userbot")

    def validate(self) -> List[str]:
        missing: List[str] = []
        if not self.bot_token:
            missing.append("BOT_TOKEN")
        if not self.admin_ids:
            missing.append("ADMIN_IDS")
        return missing

    @property
    def userbot_enabled(self) -> bool:
        return bool(self.api_id and self.api_hash and self.phone)


settings = Settings()
