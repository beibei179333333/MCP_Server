"""变换类插件：文本替换、格式化、加标题/尾注。"""
from __future__ import annotations

import re

from .base import BasePlugin, MessageContext, PluginResult
from .registry import register

URL_RE = re.compile(r"https?://\S+")
MENTION_RE = re.compile(r"@\w{4,32}")
EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002500-\U00002BEF"
    "\U00002702-\U000027B0"
    "\U0001F900-\U0001F9FF"
    "\U00002600-\U000026FF"
    "]+",
    flags=re.UNICODE,
)


@register("replace")
class ReplacePlugin(BasePlugin):
    """逐条替换。rules: [{from, to, regex}]"""

    async def process(self, ctx: MessageContext) -> PluginResult:
        rules = self.cfg.get("rules") or []
        for r in rules:
            src = r.get("from", "")
            dst = r.get("to", "")
            if not src:
                continue
            if r.get("regex"):
                try:
                    ctx.text = re.sub(src, dst, ctx.text)
                    ctx.caption = re.sub(src, dst, ctx.caption)
                except re.error:
                    continue
            else:
                ctx.text = ctx.text.replace(src, dst)
                ctx.caption = ctx.caption.replace(src, dst)
        return PluginResult.CONTINUE


@register("format")
class FormatPlugin(BasePlugin):
    """去链接 / 去 @ / 去 emoji / 折叠空行。"""

    async def process(self, ctx: MessageContext) -> PluginResult:
        def _apply(s: str) -> str:
            if self.cfg.get("strip_links"):
                s = URL_RE.sub("", s)
            if self.cfg.get("strip_mentions"):
                s = MENTION_RE.sub("", s)
            if self.cfg.get("strip_emoji"):
                s = EMOJI_RE.sub("", s)
            if self.cfg.get("collapse_newlines"):
                s = re.sub(r"\n{3,}", "\n\n", s)
            return s.strip()

        ctx.text = _apply(ctx.text)
        ctx.caption = _apply(ctx.caption)
        return PluginResult.CONTINUE


@register("caption")
class CaptionPlugin(BasePlugin):
    """统一加头/尾。"""

    async def process(self, ctx: MessageContext) -> PluginResult:
        header = self.cfg.get("header", "")
        footer = self.cfg.get("footer", "")
        if ctx.media_type == "text":
            ctx.text = f"{header}{ctx.text}{footer}"
        else:
            base = ctx.caption or ctx.text
            ctx.caption = f"{header}{base}{footer}"
        return PluginResult.CONTINUE
