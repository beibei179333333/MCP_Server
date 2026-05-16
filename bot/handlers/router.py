"""消息路由：处理非命令文本与自动回复。"""
from __future__ import annotations

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from ..utils import upsert_user
from . import autoreply, broadcast, ledger


async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await upsert_user(update)

    flow = context.user_data.get("flow")
    if flow:
        ftype = flow.get("type")
        if ftype == "broadcast":
            if await broadcast.handle_broadcast_content(update, context):
                return
        elif ftype == "ledger_add":
            if await ledger.quick_record(update, context):
                context.user_data.pop("flow", None)
                return

    # 私聊直接尝试记账
    if update.effective_chat.type == ChatType.PRIVATE:
        if await ledger.quick_record(update, context):
            return

    # 自动回复（群组 / 私聊都支持）
    await autoreply.maybe_reply(update, context)
