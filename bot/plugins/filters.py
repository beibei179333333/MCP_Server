"""过滤类插件：关键词、黑名单、媒体类型、长度、发送者。"""
from __future__ import annotations

import re

from .base import BasePlugin, MessageContext, PluginResult
from .registry import register


@register("filter")
class KeywordFilter(BasePlugin):
    """命中 keywords 中任意词才通过；命中 blacklist 直接丢弃。支持 regex。"""

    async def process(self, ctx: MessageContext) -> PluginResult:
        text = ctx.primary_text or ""
        text_low = text.lower()

        blacklist = self.cfg.get("blacklist") or []
        for w in blacklist:
            if self._hit(text_low, w):
                return PluginResult.DROP

        keywords = self.cfg.get("keywords") or []
        if keywords:
            if not any(self._hit(text_low, w) for w in keywords):
                return PluginResult.DROP
        return PluginResult.CONTINUE

    @staticmethod
    def _hit(text: str, word: str) -> bool:
        word = str(word).strip()
        if not word:
            return False
        if word.startswith("/") and word.endswith("/") and len(word) > 2:
            try:
                return re.search(word[1:-1], text, re.IGNORECASE) is not None
            except re.error:
                return False
        return word.lower() in text


@register("media")
class MediaTypeFilter(BasePlugin):
    """只允许指定媒体类型通过。"""

    async def process(self, ctx: MessageContext) -> PluginResult:
        allow = set(self.cfg.get("allow") or [])
        if allow and ctx.media_type not in allow:
            return PluginResult.DROP
        deny = set(self.cfg.get("deny") or [])
        if ctx.media_type in deny:
            return PluginResult.DROP
        return PluginResult.CONTINUE


@register("length")
class LengthFilter(BasePlugin):
    """文本长度限制。"""

    async def process(self, ctx: MessageContext) -> PluginResult:
        text = ctx.primary_text or ""
        lo = int(self.cfg.get("min", 0) or 0)
        hi = int(self.cfg.get("max", 0) or 0)
        if lo and len(text) < lo:
            return PluginResult.DROP
        if hi and len(text) > hi:
            return PluginResult.DROP
        return PluginResult.CONTINUE


@register("sender")
class SenderFilter(BasePlugin):
    """按发送者 id / username 过滤。"""

    async def process(self, ctx: MessageContext) -> PluginResult:
        allow_id = self.cfg.get("allow_ids") or []
        deny_id = self.cfg.get("deny_ids") or []
        allow_un = [u.lstrip("@").lower() for u in (self.cfg.get("allow_usernames") or [])]
        deny_un = [u.lstrip("@").lower() for u in (self.cfg.get("deny_usernames") or [])]
        un = (ctx.sender_username or "").lower()

        if deny_id and ctx.sender_id in deny_id:
            return PluginResult.DROP
        if deny_un and un in deny_un:
            return PluginResult.DROP
        if allow_id and ctx.sender_id not in allow_id:
            return PluginResult.DROP
        if allow_un and un not in allow_un:
            return PluginResult.DROP
        return PluginResult.CONTINUE
