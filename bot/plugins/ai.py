"""AI 插件：调用 OpenAI 兼容协议做改写 / 翻译 / 总结 / 润色 / 摘要。"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from ..config import settings
from .base import BasePlugin, MessageContext, PluginResult
from .registry import register

log = logging.getLogger(__name__)


_PROMPTS = {
    "rewrite": "改写下面的内容，意思不变但用不同表达方式，保持长度近似。直接输出改写结果，不要解释。",
    "translate": "把下面的内容翻译成 {target_lang}。直接输出译文，不要解释、不要原文。",
    "summarize": "用 1-3 句话总结下面的内容要点。直接输出摘要。",
    "polish": "润色下面的内容，让表达更流畅、专业，但不改变信息量。直接输出润色后的版本。",
    "tone": "把下面的内容调整为 {tone} 语气，内容主体保留。直接输出。",
    "extract": "提取下面内容的关键信息（人/事/时/地/数字/链接）。用列表格式输出。",
}


@register("ai")
class AIPlugin(BasePlugin):
    """
    cfg = {
        "action": "rewrite|translate|summarize|polish|tone|extract|custom",
        "target_lang": "en",          # action=translate 时
        "tone": "正式",                # action=tone 时
        "prompt": "...",              # action=custom 时
        "model": "gpt-4o-mini",       # 覆盖 .env 的默认模型
        "max_chars": 4000,            # 超长截断
        "on_error": "keep|drop"       # 失败时保留原文 or 丢弃
    }
    """

    async def process(self, ctx: MessageContext) -> PluginResult:
        if not settings.ai_api_key:
            log.warning("AI 插件已配置但 AI_API_KEY 为空，跳过")
            return PluginResult.CONTINUE

        text = ctx.primary_text
        if not text:
            return PluginResult.CONTINUE

        max_chars = int(self.cfg.get("max_chars", 4000))
        if len(text) > max_chars:
            text = text[:max_chars]

        action = self.cfg.get("action", "rewrite")
        if action == "custom":
            sys_prompt = self.cfg.get("prompt", "请处理以下内容。直接输出结果。")
        else:
            tpl = _PROMPTS.get(action)
            if not tpl:
                log.warning("AI 插件未知 action: %s", action)
                return PluginResult.CONTINUE
            sys_prompt = tpl.format(
                target_lang=self.cfg.get("target_lang", "English"),
                tone=self.cfg.get("tone", "正式"),
            )

        model = self.cfg.get("model") or settings.ai_model
        result = await _chat(sys_prompt, text, model)
        if result is None:
            if self.cfg.get("on_error", "keep") == "drop":
                return PluginResult.DROP
            return PluginResult.CONTINUE

        # 应用到合适字段
        if ctx.media_type == "text":
            ctx.text = result
        else:
            ctx.caption = result
        return PluginResult.CONTINUE


async def _chat(system: str, user: str, model: str) -> Optional[str]:
    url = settings.ai_base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.ai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.7,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.ai_timeout) as client:
            r = await client.post(url, headers=headers, json=payload)
            if r.status_code != 200:
                log.warning("AI %s: %s", r.status_code, r.text[:300])
                return None
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001
        log.warning("AI 请求失败: %s", e)
        return None


# 暴露给 /ai 命令复用
async def quick_chat(prompt: str, system: str = "你是有帮助的助手。") -> Optional[str]:
    if not settings.ai_api_key:
        return None
    return await _chat(system, prompt, settings.ai_model)
