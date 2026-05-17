"""消息路由：群组反垃圾 / 验证码 / 入账 / 自动回复 / 群发上下文。"""
from __future__ import annotations

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from ..utils import upsert_user
from . import autoreply, broadcast, group, ledger


async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await upsert_user(update)

    # 1) 群里反垃圾（命中即删除并停止）
    if update.effective_chat.type in ("group", "supergroup"):
        if await group.antispam_check(update, context):
            return
        # 2) 数字回复可能是 math 验证码
        if await group.captcha_text_answer(update, context):
            return

    # 3) flow 状态
    flow = context.user_data.get("flow")
    if flow:
        ftype = flow.get("type")
        if ftype in ("broadcast", "broadcast_tag_pick"):
            if await broadcast.handle_broadcast_content(update, context):
                return
        elif ftype == "ledger_add":
            if await ledger.quick_record(update, context):
                context.user_data.pop("flow", None)
                return
        elif ftype in ("fw_wizard", "fw_edit"):
            from . import fw_editor
            if await fw_editor.handle_wizard_text(update, context):
                return

    # 4) 私聊：尝试解析为记账
    if update.effective_chat.type == ChatType.PRIVATE:
        if await ledger.quick_record(update, context):
            return

    # 5) 自动回复
    await autoreply.maybe_reply(update, context)
