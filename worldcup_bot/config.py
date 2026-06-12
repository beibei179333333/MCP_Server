"""Runtime configuration for the World Cup Telegram bot.

All settings are read from environment variables (optionally seeded from a
local ``.env`` file). Nothing here requires extra dependencies — the ``.env``
parser is intentionally tiny so the bot runs with just the stdlib + requests.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    """Populate os.environ from a simple KEY=VALUE .env file (no deps)."""
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # don't override variables already set in the real environment
        os.environ.setdefault(key, value)


def _get_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on", "y"}


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip())
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    telegram_token: str = ""
    football_data_key: str = ""
    provider: str = "football-data"          # football-data | demo
    competition: str = "WC"                   # football-data competition code
    poll_interval: int = 60                   # seconds between data polls
    reminder_minutes: int = 15                # pre-kickoff reminder window
    timezone: str = "UTC"                     # display timezone (IANA name)
    default_lang: str = "zh"                  # zh | en
    db_path: str = "worldcup_bot.db"
    admin_chat_id: str = ""                   # optional, enables /broadcast
    demo_seconds_per_match: int = 120         # demo mode: accelerated match length
    request_timeout: int = 20

    warnings: list = field(default_factory=list)

    @classmethod
    def load(cls, dotenv: str = ".env") -> "Config":
        _load_dotenv(dotenv)
        cfg = cls(
            telegram_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
            football_data_key=os.environ.get("FOOTBALL_DATA_API_KEY", "").strip(),
            provider=os.environ.get("PROVIDER", "football-data").strip().lower(),
            competition=os.environ.get("COMPETITION", "WC").strip(),
            poll_interval=_get_int("POLL_INTERVAL_SECONDS", 60),
            reminder_minutes=_get_int("REMINDER_MINUTES", 15),
            timezone=os.environ.get("TIMEZONE", "UTC").strip() or "UTC",
            default_lang=os.environ.get("DEFAULT_LANG", "zh").strip().lower(),
            db_path=os.environ.get("DB_PATH", "worldcup_bot.db").strip(),
            admin_chat_id=os.environ.get("ADMIN_CHAT_ID", "").strip(),
            demo_seconds_per_match=_get_int("DEMO_SECONDS_PER_MATCH", 120),
            request_timeout=_get_int("REQUEST_TIMEOUT", 20),
        )

        # Auto-fallback: no API key and not explicitly demo -> use demo data so
        # the bot still runs end-to-end without a paid/registered data source.
        if cfg.provider == "football-data" and not cfg.football_data_key:
            cfg.provider = "demo"
            cfg.warnings.append(
                "未设置 FOOTBALL_DATA_API_KEY，已自动切换到 demo（演示）数据源。"
                "如需真实赛事数据，请到 https://www.football-data.org/ 申请免费 Key。"
            )
        # In demo mode, if the user didn't pin a poll interval, use a short one
        # so the accelerated live match's events are all observable.
        if cfg.is_demo and "POLL_INTERVAL_SECONDS" not in os.environ:
            cfg.poll_interval = 12
        if cfg.poll_interval < 5:
            cfg.poll_interval = 5
        if cfg.default_lang not in {"zh", "en"}:
            cfg.default_lang = "zh"
        return cfg

    @property
    def is_demo(self) -> bool:
        return self.provider == "demo"
