"""高级插件：去重 / 延迟 / 原始文本 / 按钮转文本。"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import deque

from .base import BasePlugin, MessageContext, PluginResult
from .registry import register

log = logging.getLogger(__name__)

# 全局去重缓存（按规则 id 分桶，每桶最近 N 条哈希）
_DEDUP_CACHE: dict[int, deque] = {}


@register("dedupe")
class DedupePlugin(BasePlugin):
    """重复内容去重。
    cfg = {"window": 200, "by": "text|hash"}
    - window: 记忆最近 N 条
    - by: 按文本去重，或按媒体+文本组合哈希
    """

    async def process(self, ctx: MessageContext) -> PluginResult:
        rule_id = ctx.extra.get("rule_id", 0)
        window = int(self.cfg.get("window", 200))
        mode = self.cfg.get("by", "text")
        if mode == "hash" and ctx.media_bytes:
            digest = hashlib.sha1(
                (ctx.primary_text or "").encode("utf-8", "ignore")
                + ctx.media_bytes
            ).hexdigest()
        else:
            digest = hashlib.sha1(
                (ctx.primary_text or "").strip().encode("utf-8", "ignore")
            ).hexdigest()

        buf = _DEDUP_CACHE.setdefault(rule_id, deque(maxlen=window))
        if digest in buf:
            return PluginResult.DROP
        buf.append(digest)
        return PluginResult.CONTINUE


@register("delay")
class DelayPlugin(BasePlugin):
    """转发前等待 N 秒。
    cfg = {"seconds": 5, "jitter": 2}
    """

    async def process(self, ctx: MessageContext) -> PluginResult:
        secs = float(self.cfg.get("seconds", 0))
        jitter = float(self.cfg.get("jitter", 0))
        if jitter:
            import random
            secs += random.uniform(0, jitter)
        if secs > 0:
            await asyncio.sleep(min(secs, 300))  # 上限 5min 防误填
        return PluginResult.CONTINUE


@register("raw")
class RawPlugin(BasePlugin):
    """提取纯文本：去 Markdown / HTML 标签 / 多余空白。"""

    async def process(self, ctx: MessageContext) -> PluginResult:
        import re
        def _strip(s: str) -> str:
            s = re.sub(r"<[^>]+>", "", s or "")        # HTML
            s = re.sub(r"[*_`~]+", "", s)              # Markdown
            s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", s)  # markdown link
            s = re.sub(r"\s{2,}", " ", s)
            return s.strip()
        ctx.text = _strip(ctx.text)
        ctx.caption = _strip(ctx.caption)
        return PluginResult.CONTINUE
