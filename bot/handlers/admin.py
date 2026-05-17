"""管理员面板：统计 / 用户群组列表 / chat 追踪。"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import func, select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

from ..database import (
    AutoReply,
    BroadcastJob,
    Chat,
    ForwardRule,
    LedgerEntry,
    SessionLocal,
    User,
)
from ..keyboards import back_home
from ..utils import admin_only, is_admin

log = logging.getLogger(__name__)


def _admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👥 用户列表", callback_data="admin:users"),
                InlineKeyboardButton("💬 群组列表", callback_data="admin:chats"),
            ],
            [
                InlineKeyboardButton("📊 全局统计", callback_data="admin:stats"),
                InlineKeyboardButton("📜 群发历史", callback_data="admin:broadcasts"),
            ],
            [InlineKeyboardButton("« 返回", callback_data="menu:home")],
        ]
    )


async def open_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = "⚙️ *管理面板*\n选择要查看的内容："
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=_admin_keyboard()
        )
    else:
        await update.effective_message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=_admin_keyboard()
        )


@admin_only
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await open_admin_panel(update, context)


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as s:
        users_total = (await s.execute(select(func.count(User.id)))).scalar() or 0
        chats_total = (
            await s.execute(select(func.count(Chat.id)).where(Chat.is_active.is_(True)))
        ).scalar() or 0
        rules_total = (await s.execute(select(func.count(ForwardRule.id)))).scalar() or 0
        ar_total = (await s.execute(select(func.count(AutoReply.id)))).scalar() or 0
        ledger_total = (await s.execute(select(func.count(LedgerEntry.id)))).scalar() or 0
        forwards_done = (
            await s.execute(select(func.coalesce(func.sum(ForwardRule.forwarded_count), 0)))
        ).scalar() or 0
        last_broadcast = (
            await s.execute(
                select(BroadcastJob).order_by(BroadcastJob.id.desc()).limit(1)
            )
        ).scalar_one_or_none()

    bc_line = "—"
    if last_broadcast:
        bc_line = (
            f"#{last_broadcast.id} · {last_broadcast.sent}/{last_broadcast.total} "
            f"({last_broadcast.started_at.strftime('%m-%d %H:%M')})"
        )

    text = (
        "📊 *全局统计*\n\n"
        f"👥 用户：*{users_total}*\n"
        f"💬 群组：*{chats_total}*\n"
        f"📡 搬运规则：*{rules_total}*（已转 {forwards_done} 条）\n"
        f"💬 自动回复：*{ar_total}* 条\n"
        f"📒 记账流水：*{ledger_total}* 条\n"
        f"📣 上次群发：{bc_line}\n"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=back_home()
        )
    else:
        await update.effective_message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=back_home()
        )


@admin_only
async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_stats(update, context)


async def _render_users(page: int):
    from ..utils import paginate, pager_keyboard, short
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                select(User).order_by(User.last_seen.desc())
            )
        ).scalars().all()
    if not rows:
        return "📭 暂无用户", None
    chunk, page, pages = paginate(rows, page, per_page=15)
    lines = [f"👥 *用户列表* — {len(rows)} 人 · 第 {page}/{pages} 页\n"]
    for u in chunk:
        name = short(" ".join(filter(None, [u.first_name, u.last_name])) or "—", 24)
        handle = f"@{u.username}" if u.username else f"`{u.id}`"
        flag = ""
        if u.is_blocked:
            flag = " 🚫"
        elif u.is_admin:
            flag = " 👑"
        lines.append(f"• {name} · {handle}{flag}")
    return "\n".join(lines), pager_keyboard("ulist", page, pages)


@admin_only
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text, kb = await _render_users(1)
    await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


async def _render_chats(page: int):
    from ..utils import paginate, pager_keyboard, short
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                select(Chat).where(Chat.is_active.is_(True)).order_by(Chat.joined_at.desc())
            )
        ).scalars().all()
    if not rows:
        return "📭 机器人尚未加入任何群组 / 频道", None
    chunk, page, pages = paginate(rows, page, per_page=15)
    lines = [f"💬 *关联群组 / 频道* — {len(rows)} 个 · 第 {page}/{pages} 页\n"]
    for c in chunk:
        handle = f"@{c.username}" if c.username else f"`{c.id}`"
        lines.append(f"• [{c.type}] {short(c.title or '—', 30)} · {handle}")
    return "\n".join(lines), pager_keyboard("clist", page, pages)


@admin_only
async def chats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text, kb = await _render_chats(1)
    await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


async def pager_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """统一处理所有 *list:<page> 翻页。"""
    q = update.callback_query
    await q.answer()
    parts = q.data.split(":")
    prefix = parts[0]
    try:
        page = int(parts[1])
    except (ValueError, IndexError):
        page = 1
    if prefix == "ulist":
        text, kb = await _render_users(page)
    elif prefix == "clist":
        text, kb = await _render_chats(page)
    elif prefix == "fwlist":
        from .forward_admin import _render_fwlist
        text, kb = await _render_fwlist(page)
    else:
        return
    try:
        await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    except Exception:
        pass


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        await query.edit_message_text("⛔ 仅管理员可用", reply_markup=back_home())
        return
    target = query.data.split(":", 1)[1]
    if target == "users":
        await users_cmd(update, context)
    elif target == "chats":
        await chats_cmd(update, context)
    elif target == "stats":
        await show_stats(update, context)
    elif target == "broadcasts":
        await _list_broadcasts(update, context)
    else:
        await open_admin_panel(update, context)


async def _list_broadcasts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                select(BroadcastJob).order_by(BroadcastJob.id.desc()).limit(10)
            )
        ).scalars().all()
    if not rows:
        text = "📭 暂无群发记录"
    else:
        lines = ["📜 *最近群发记录*\n"]
        for j in rows:
            finished = j.finished_at.strftime("%m-%d %H:%M") if j.finished_at else "进行中"
            lines.append(
                f"• #{j.id} {j.target_type} · {j.sent}✅/{j.failed}❌/{j.total} · {finished}"
            )
        text = "\n".join(lines)
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=back_home()
        )
    else:
        await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ---------- chat 加入 / 离开追踪 ----------

async def track_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """监听机器人在群组中的状态变化。"""
    upd = update.my_chat_member
    if not upd:
        return
    chat = upd.chat
    new_status = upd.new_chat_member.status

    async with SessionLocal() as s:
        existing = await s.get(Chat, chat.id)
        if new_status in ("member", "administrator"):
            if existing:
                existing.is_active = True
                existing.title = chat.title
                existing.username = chat.username
                existing.type = chat.type
            else:
                s.add(
                    Chat(
                        id=chat.id,
                        type=chat.type,
                        title=chat.title,
                        username=chat.username,
                        is_active=True,
                    )
                )
            log.info("加入 chat: %s (%s)", chat.title, chat.id)
        elif new_status in ("left", "kicked"):
            if existing:
                existing.is_active = False
            log.info("离开 chat: %s (%s)", chat.title, chat.id)
        await s.commit()
