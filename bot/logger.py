"""统一的日志配置。"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from .config import BASE_DIR, settings


def setup_logging() -> logging.Logger:
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    fmt = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    formatter = logging.Formatter(fmt, "%Y-%m-%d %H:%M:%S")

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    root.addHandler(stream)

    file_handler = logging.FileHandler(log_dir / "bot.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    for noisy in ("httpx", "telethon", "apscheduler", "telegram.ext"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return logging.getLogger("bot")
