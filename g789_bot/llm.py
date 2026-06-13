"""Claude backend for the bot.

Each G789 scenario's full ``SKILL.md`` becomes the system prompt; the per-chat
message history is replayed on every turn (the Messages API is stateless). The
large, per-scenario system prompt is prompt-cached so repeated turns in the same
conversation only pay the ~0.1x cache-read price for it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import anthropic

from .config import Config
from .skills import Skill

# Conversational wrapper placed *before* the scenario body. Stable across the
# whole conversation, so it sits at the front of the cached prefix.
_PREAMBLE = (
    "你正在通过 Telegram 聊天机器人，以下面定义的「场景助手」身份与用户对话。\n"
    "You are operating as the scenario assistant defined below, talking to a user "
    "over a Telegram chat bot.\n\n"
    "Conversation rules:\n"
    "- Reply in the user's language (default to 简体中文 if unclear).\n"
    "- Be conversational and concise — this is a chat window, not a document. "
    "Use short paragraphs; avoid dumping the entire pipeline at once.\n"
    "- Drive the scenario workflow naturally: ask for what you need, then deliver.\n"
    "- Respond directly with your reply only. Do not expose internal scaffolding, "
    "raw Callback JSON, or step bookkeeping unless the user explicitly asks for it.\n"
    "- Telegram supports basic Markdown: *bold*, _italic_, `code`. Keep formatting light.\n\n"
    "===== 场景定义 / SCENARIO DEFINITION =====\n"
)


class LLM:
    def __init__(self, config: Config):
        self._config = config
        # AsyncAnthropic resolves ANTHROPIC_API_KEY from the environment.
        self._client = anthropic.AsyncAnthropic()

    def system_for(self, skill: Skill) -> list[dict]:
        """Two-block system prompt; the scenario body carries the cache breakpoint."""
        return [
            {"type": "text", "text": _PREAMBLE},
            {
                "type": "text",
                "text": skill.body,
                "cache_control": {"type": "ephemeral"},
            },
        ]

    async def stream_reply(
        self, skill: Skill, history: list[dict]
    ) -> AsyncIterator[str]:
        """Yield text chunks for the assistant's reply given the chat history."""
        async with self._client.messages.stream(
            model=self._config.model,
            max_tokens=self._config.max_output_tokens,
            system=self.system_for(skill),
            output_config={"effort": self._config.effort},
            messages=history,
        ) as stream:
            async for text in stream.text_stream:
                yield text
