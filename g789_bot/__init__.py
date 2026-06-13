"""G789 scenario-skill Telegram bot.

Serves all 500 self-contained G789 scenario skills (S-001 … S-500) through a
Telegram chat interface backed by Claude.
"""

__all__ = ["Catalog", "Config", "build_application"]

from .config import Config
from .skills import Catalog


def build_application(config: "Config"):  # lazy import to avoid hard dep at import time
    from .bot import build_application as _build

    return _build(config)
