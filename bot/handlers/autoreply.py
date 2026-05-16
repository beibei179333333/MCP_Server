"""关键词自动回复。"""
from __future__ import annotations

import logging
import re

from sqlalchemy import select
from telegram import Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

from ..database import AutoReply, SessionLocal
from ..keyboards import back_home
from ..utils import is_admin

log = logging.getLogger(__name__)

PANEL = """\
💬 *自动回复*

命令：
• `/ar_add 关键词 ::: 回复内容` — 添加规则
• `/ar_add_re 正则 ::: 回复内容` — 正则匹配
• `/ar_list` — 列出当前群规则
• `/ar_del <id>` — 删除规则
• `/ar_toggle <id>` — 启用 / 停用

群组中由管理员配置；私聊中将作为全局规则（仅 bot 管理员可建）。
"""


async def open_autoreply_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.edit_message_text(
            PANEL, parse_mode=ParseMode.MARKDOWN, reply_markup=back_home()
        )
    else:
        await update.effective_message.reply_text(
            PANEL, parse_mode=ParseMode.MARKDOWN, reply_markup=back_home()
        )


def _scope_for(update: Update) -> int | None:
    chat = update.effective_chat
    if chat.type == ChatType.PRIVATE:
        return None
    return chat.id


async def _can_manage(update: Update) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    if is_admin(user.id):
        return True
    if chat.type == ChatType.PRIVATE:
        return False
    try:
        member = await chat.get_member(user.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _add(update, context, match_type="contains")


async def add_re_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _add(update, context, match_type="regex")


async def _add(update: Update, context: ContextTypes.DEFAULT_TYPE, match_type: str) -> None:
    if not await _can_manage(update):
        await update.effective_message.reply_text("⛔ 仅群管理员可配置")
        return

    raw = update.effective_message.text or ""
    parts = raw.split(maxsplit=1)
    if len(parts) < 2 or ":::" not in parts[1]:
        await update.effective_message.reply_text(
            "用法：`/ar_add 关键词 ::: 回复内容`", parse_mode=ParseMode.MARKDOWN
        )
        return
    pattern, _, reply = parts[1].partition(":::")
    pattern = pattern.strip()
    reply = reply.strip()
    if not pattern or not reply:
        await update.effective_message.reply_text("⚠️ 关键词与回复都不能为空")
        return

    if match_type == "regex":
        try:
            re.compile(pattern)
        except re.error as e:
            await update.effective_message.reply_text(f"❌ 正则语法错误：{e}")
            return

    scope = _scope_for(update)
    async with SessionLocal() as s:
        rule = AutoReply(
            scope_chat_id=scope,
            pattern=pattern,
            match_type=match_type,
            reply_text=reply,
        )
        s.add(rule)
        await s.commit()
        await s.refresh(rule)
    await update.effective_message.reply_text(
        f"✅ 已添加规则 #{rule.id}（{match_type}）"
    )


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    scope = _scope_for(update)
    async with SessionLocal() as s:
        stmt = select(AutoReply)
        if scope is None:
            stmt = stmt.where(AutoReply.scope_chat_id.is_(None))
        else:
            stmt = stmt.where(AutoReply.scope_chat_id == scope)
        rules = (await s.execute(stmt.order_by(AutoReply.id))).scalars().all()
    if not rules:
        await update.effective_message.reply_text("📭 暂无规则")
        return
    lines = ["💬 *规则列表*\n"]
    for r in rules:
        status = "✅" if r.enabled else "🚫"
        tag = "正则" if r.match_type == "regex" else "包含"
        preview = r.reply_text if len(r.reply_text) <= 40 else r.reply_text[:40] + "…"
        lines.append(f"{status} `#{r.id}` [{tag}] `{r.pattern}` → {preview}  ({r.hits}次)")
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def del_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _can_manage(update):
        await update.effective_message.reply_text("⛔ 仅群管理员可操作")
        return
    if not context.args:
        await update.effective_message.reply_text("用法：`/ar_del <id>`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        rid = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ id 必须是数字")
        return
    async with SessionLocal() as s:
        rule = await s.get(AutoReply, rid)
        if not rule:
            await update.effective_message.reply_text("❌ 规则不存在")
            return
        scope = _scope_for(update)
        if rule.scope_chat_id != scope and not is_admin(update.effective_user.id):
            await update.effective_message.reply_text("⛔ 无权操作其他群规则")
            return
        await s.delete(rule)
        await s.commit()
    await update.effective_message.reply_text(f"🗑 已删除 #{rid}")


async def toggle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _can_manage(update):
        await update.effective_message.reply_text("⛔ 仅群管理员可操作")
        return
    if not context.args:
        await update.effective_message.reply_text("用法：`/ar_toggle <id>`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        rid = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ id 必须是数字")
        return
    async with SessionLocal() as s:
        rule = await s.get(AutoReply, rid)
        if not rule:
            await update.effective_message.reply_text("❌ 规则不存在")
            return
        rule.enabled = not rule.enabled
        await s.commit()
        state = "启用 ✅" if rule.enabled else "停用 🚫"
    await update.effective_message.reply_text(f"#{rid} 已 {state}")


def _match(rule: AutoReply, text: str) -> bool:
    if rule.match_type == "regex":
        try:
            return re.search(rule.pattern, text, re.IGNORECASE) is not None
        except re.error:
            return False
    return rule.pattern.lower() in text.lower()


async def maybe_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """检查消息是否触发自动回复。返回 True 表示已回复。"""
    msg = update.effective_message
    if not msg or not msg.text:
        return False
    text = msg.text
    chat_id = update.effective_chat.id

    async with SessionLocal() as s:
        stmt = select(AutoReply).where(
            AutoReply.enabled.is_(True),
            (AutoReply.scope_chat_id == chat_id) | (AutoReply.scope_chat_id.is_(None)),
        )
        rules = (await s.execute(stmt)).scalars().all()

        for rule in rules:
            if _match(rule, text):
                rule.hits += 1
                await s.commit()
                try:
                    await msg.reply_text(rule.reply_text)
                except Exception as e:
                    log.warning("AutoReply 发送失败: %s", e)
                return True
    return False
