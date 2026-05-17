"""集中化配置。从 .env 读取，提供类型安全的访问。"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
load_dotenv(BASE_DIR / ".env")


def _split_ids(raw: str) -> List[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def _bool(raw: Optional[str], default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "y", "on")


@dataclass
class Settings:
    # ---- Bot 核心 ----
    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    admin_ids: List[int] = field(
        default_factory=lambda: _split_ids(os.getenv("ADMIN_IDS", ""))
    )

    # ---- User-bot ----
    api_id: int = field(default_factory=lambda: int(os.getenv("TG_API_ID", "0") or 0))
    api_hash: str = field(default_factory=lambda: os.getenv("TG_API_HASH", ""))
    phone: str = field(default_factory=lambda: os.getenv("TG_PHONE", ""))
    tg_password: str = field(default_factory=lambda: os.getenv("TG_PASSWORD", ""))

    # ---- 数据库 ----
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", f"sqlite+aiosqlite:///{DATA_DIR / 'bot.db'}"
        )
    )

    # ---- 时区 / 调度 ----
    timezone: str = field(default_factory=lambda: os.getenv("TIMEZONE", "Asia/Shanghai"))

    # ---- 群发 ----
    broadcast_interval_ms: int = field(
        default_factory=lambda: int(os.getenv("BROADCAST_INTERVAL_MS", "80"))
    )
    broadcast_batch: int = field(
        default_factory=lambda: int(os.getenv("BROADCAST_BATCH", "30"))
    )
    broadcast_concurrency: int = field(
        default_factory=lambda: int(os.getenv("BROADCAST_CONCURRENCY", "10"))
    )

    # ---- 群组管理 ----
    enable_captcha: bool = field(
        default_factory=lambda: _bool(os.getenv("ENABLE_CAPTCHA"), True)
    )
    captcha_timeout: int = field(
        default_factory=lambda: int(os.getenv("CAPTCHA_TIMEOUT", "120"))
    )
    enable_anti_spam: bool = field(
        default_factory=lambda: _bool(os.getenv("ENABLE_ANTI_SPAM"), True)
    )

    # ---- 订阅 ----
    subscription_enabled: bool = field(
        default_factory=lambda: _bool(os.getenv("SUBSCRIPTION_ENABLED"), True)
    )
    default_trial_days: int = field(
        default_factory=lambda: int(os.getenv("DEFAULT_TRIAL_DAYS", "7"))
    )

    # ---- Web ----
    web_enabled: bool = field(
        default_factory=lambda: _bool(os.getenv("WEB_ENABLED"), True)
    )
    web_host: str = field(default_factory=lambda: os.getenv("WEB_HOST", "0.0.0.0"))
    web_port: int = field(default_factory=lambda: int(os.getenv("WEB_PORT", "8000")))
    web_secret: str = field(
        default_factory=lambda: os.getenv("WEB_SECRET", "") or secrets.token_urlsafe(32)
    )
    web_username: str = field(
        default_factory=lambda: os.getenv("WEB_USERNAME", "admin")
    )
    web_password: str = field(default_factory=lambda: os.getenv("WEB_PASSWORD", ""))

    # ---- AI（OpenAI 兼容协议：OpenAI/DeepSeek/Moonshot/智谱/Together…） ----
    ai_provider: str = field(default_factory=lambda: os.getenv("AI_PROVIDER", "openai"))
    ai_api_key: str = field(default_factory=lambda: os.getenv("AI_API_KEY", ""))
    ai_base_url: str = field(default_factory=lambda: os.getenv("AI_BASE_URL", "https://api.openai.com/v1"))
    ai_model: str = field(default_factory=lambda: os.getenv("AI_MODEL", "gpt-4o-mini"))
    ai_timeout: int = field(default_factory=lambda: int(os.getenv("AI_TIMEOUT", "30")))

    # ---- 返佣 / MMO ----
    referral_commission: float = field(
        default_factory=lambda: float(os.getenv("REFERRAL_COMMISSION", "0.20"))
    )
    referral_min_withdraw: float = field(
        default_factory=lambda: float(os.getenv("REFERRAL_MIN_WITHDRAW", "50"))
    )

    # ---- 多语言 ----
    default_lang: str = field(default_factory=lambda: os.getenv("DEFAULT_LANG", "zh"))

    # ---- 日志 ----
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_retention_days: int = field(
        default_factory=lambda: int(os.getenv("LOG_RETENTION_DAYS", "14"))
    )

    # ---- 内部路径 ----
    session_path: Path = field(default_factory=lambda: DATA_DIR / "userbot")
    media_dir: Path = field(default_factory=lambda: DATA_DIR / "media")

    def validate(self) -> List[str]:
        missing: List[str] = []
        if not self.bot_token:
            missing.append("BOT_TOKEN")
        # ADMIN_IDS 推荐但非必需：留空时仅警告，部分管理功能不可用
        return missing

    @property
    def userbot_enabled(self) -> bool:
        return bool(self.api_id and self.api_hash and self.phone)

    @property
    def effective_web_password(self) -> str:
        if self.web_password:
            return self.web_password
        # 默认从 secret 派生，避免明文裸奔
        import hashlib
        return hashlib.sha256(self.web_secret.encode()).hexdigest()[:16]


settings = Settings()
settings.media_dir.mkdir(exist_ok=True)
