"""按钮相关插件：
- buttons:    给转发消息附加内联按钮（最终在 userbot 发送时读取）
- btn2text:   把原消息的按钮转为纯文本附加到正文
"""
from __future__ import annotations

from .base import BasePlugin, MessageContext, PluginResult
from .registry import register


@register("buttons")
class ButtonsPlugin(BasePlugin):
    """
    cfg = {"rows": [[{"label":"X","url":"https://..."}, ...], ...]}
    用户号也能发带 url 按钮的消息（Telethon `buttons=`），bot 发更全。
    实际渲染在 userbot.py 中读取 ctx.extra["buttons"]。
    """

    async def process(self, ctx: MessageContext) -> PluginResult:
        rows = self.cfg.get("rows") or []
        if rows:
            ctx.extra["buttons"] = rows
        return PluginResult.CONTINUE


@register("btn2text")
class ButtonsToTextPlugin(BasePlugin):
    """把原消息的按钮转成 "标签: URL" 行追加到正文。
    源消息的按钮已经在 userbot 取消息时放入 ctx.extra["source_buttons"]。
    """

    async def process(self, ctx: MessageContext) -> PluginResult:
        src = ctx.extra.get("source_buttons") or []
        if not src:
            return PluginResult.CONTINUE
        lines = ["", "🔗 *相关链接：*"]
        for row in src:
            for btn in row:
                label = btn.get("label", "")
                url = btn.get("url", "")
                if url and label:
                    lines.append(f"• {label}: {url}")
                elif label:
                    lines.append(f"• {label}")
        appendix = "\n".join(lines)
        if ctx.media_type == "text":
            ctx.text = (ctx.text or "") + "\n" + appendix
        else:
            ctx.caption = (ctx.caption or "") + "\n" + appendix
        return PluginResult.CONTINUE
