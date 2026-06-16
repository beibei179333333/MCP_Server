"""Runtime configuration for the G789 Telegram bot, read from the environment.

Nothing here is secret-by-default except the two tokens, which are never logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _csv(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


@dataclass(frozen=True)
class Config:
    telegram_token: str
    anthropic_api_key: str
    model: str = "claude-opus-4-8"
    effort: str = "medium"          # low | medium | high | max
    max_history_turns: int = 16     # user+assistant messages kept per chat
    max_output_tokens: int = 4000
    blocked_categories: frozenset[str] = frozenset()
    admin_ids: frozenset[int] = frozenset()

    @classmethod
    def from_env(cls) -> "Config":
        telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        # The Anthropic SDK reads ANTHROPIC_API_KEY itself; we only surface it
        # here so we can fail fast with a clear message if it's missing.
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()

        admin_ids = frozenset(
            int(x) for x in _csv(os.environ.get("G789_ADMIN_IDS", "")) if x.isdigit()
        )

        return cls(
            telegram_token=telegram_token,
            anthropic_api_key=anthropic_key,
            model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8").strip(),
            effort=os.environ.get("G789_EFFORT", "medium").strip() or "medium",
            max_history_turns=int(os.environ.get("G789_MAX_HISTORY_TURNS", "16")),
            max_output_tokens=int(os.environ.get("G789_MAX_OUTPUT_TOKENS", "4000")),
            blocked_categories=frozenset(_csv(os.environ.get("G789_BLOCKED_CATEGORIES", ""))),
            admin_ids=admin_ids,
        )

    def missing(self) -> list[str]:
        """Return the names of required settings that are absent."""
        missing = []
        if not self.telegram_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        return missing
