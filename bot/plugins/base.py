"""插件基类与消息上下文。"""
from __future__ import annotations

import enum
import io
from dataclasses import dataclass, field
from typing import Any, Optional


class PluginResult(enum.Enum):
    CONTINUE = "continue"
    DROP = "drop"           # 丢弃此消息，不再转发
    HALT = "halt"           # 停止后续插件，但仍转发


@dataclass
class MessageContext:
    """跨插件共享的消息上下文。"""

    text: str = ""
    media_type: str = "text"   # text / photo / video / document / audio / voice / sticker / etc.
    media_bytes: Optional[bytes] = None
    media_filename: Optional[str] = None
    media_mime: Optional[str] = None
    caption: str = ""
    sender_id: Optional[int] = None
    sender_username: Optional[str] = None
    chat_id: Optional[int] = None
    chat_username: Optional[str] = None
    message_id: Optional[int] = None
    extra: dict = field(default_factory=dict)

    @property
    def primary_text(self) -> str:
        return self.text or self.caption


class BasePlugin:
    name: str = "base"

    def __init__(self, cfg: dict | None = None) -> None:
        self.cfg = cfg or {}

    async def process(self, ctx: MessageContext) -> PluginResult:
        return PluginResult.CONTINUE


class PluginChain:
    def __init__(self, plugins: list[BasePlugin]) -> None:
        self.plugins = plugins

    async def run(self, ctx: MessageContext) -> bool:
        """返回 True 表示应继续转发；False 表示丢弃。"""
        for p in self.plugins:
            try:
                res = await p.process(ctx)
            except Exception:  # noqa: BLE001
                import logging
                logging.getLogger("plugins").exception(
                    "插件 %s 处理失败", p.name
                )
                continue
            if res == PluginResult.DROP:
                return False
            if res == PluginResult.HALT:
                return True
        return True
