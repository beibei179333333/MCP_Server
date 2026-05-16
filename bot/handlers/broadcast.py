"""群发：即时 / 定时 / 标签分群 / 内联按钮，节流 + 失败标记。"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, RetryAfter
from telegram.ext import ContextTypes

from ..config import settings
from ..database import BroadcastJob, Chat, SessionLocal, User
from ..keyboards import back_home
from ..utils import admin_only, is_admin

log = logging.getLogger(__name__)


def _panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👥 所有用户", callback_data="bc:target:users"),
                InlineKeyboardButton("💬 所有群组", callback_data="bc:target:chats"),
            ],
            [
                InlineKeyboardButton("🌐 全部", callback_data="bc:target:both"),
                InlineKeyboardButton("🏷 按标签", callback_data="bc:target:tag"),
            ],
            [InlineKeyboardButton("📜 历史 / 草稿", callback_data="bc:list")],
            [InlineKeyboardButton("« 返回", callback_data="menu:home")],
        ]
    )


PANEL = """\
📣 *群发中心*

支持：
• 即时群发：选择目标后直接发消息
• 定时群发：消息附加 `@schedule 2030-01-01 10:00`
• 内联按钮：消息附加 `@buttons [["按钮1","https://..."], ["按钮2","cb_data"]]`
• 标签分群：`/bc_tag <tag>` 后发消息

命令：
  /broadcast users 内容
  /broadcast chats 内容（或回复一条消息）
  /broadcast both 内容
  /broadcast tag VIP 内容
"""


async def open_broadcast_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.edit_message_text(
            PANEL, parse_mode=ParseMode.MARKDOWN, reply_markup=_panel_keyboard()
        )
    else:
        await update.effective_message.reply_text(
            PANEL, parse_mode=ParseMode.MARKDOWN, reply_markup=_panel_keyboard()
        )


@admin_only
async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await open_broadcast_panel(update, context)
        return
    target = context.args[0].lower()
    if target not in ("users", "chats", "both", "tag"):
        await update.effective_message.reply_text("用法：`/broadcast <users|chats|both|tag> 内容`")
        return
    tag = None
    idx = 1
    if target == "tag":
        if len(context.args) < 2:
            await update.effective_message.reply_text("用法：`/broadcast tag <标签名> 内容`")
            return
        tag = context.args[1]
        idx = 2
    text = " ".join(context.args[idx:]).strip()
    replied = update.effective_message.reply_to_message
    if not text and not replied:
        await update.effective_message.reply_text("⚠️ 请提供内容或回复一条消息")
        return
    await _enqueue_or_run(update, context, target, text=text, replied=replied, tag=tag)


async def broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        await query.edit_message_text("⛔ 仅管理员", reply_markup=back_home())
        return
    parts = query.data.split(":")
    if len(parts) >= 3 and parts[1] == "target":
        target = parts[2]
        if target == "tag":
            context.user_data["flow"] = {"type": "broadcast_tag_pick"}
            await query.edit_message_text(
                "🏷 请输入要群发的*标签名*（或发送 `/cancel` 取消）：",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        context.user_data["flow"] = {"type": "broadcast", "target": target}
        await query.edit_message_text(
            f"📤 目标：*{target}*\n请发送内容（支持 @schedule / @buttons），/cancel 取消。",
            parse_mode=ParseMode.MARKDOWN,
        )
    elif parts[1] == "list":
        await _list_jobs(update, context)
    else:
        await open_broadcast_panel(update, context)


async def handle_broadcast_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    flow = context.user_data.get("flow")
    if not flow:
        return False
    if flow.get("type") == "broadcast_tag_pick":
        tag = (update.effective_message.text or "").strip()
        if not tag:
            return True
        context.user_data["flow"] = {"type": "broadcast", "target": "tag", "tag": tag}
        await update.effective_message.reply_text(
            f"✅ 标签 *{tag}* 已设定，请发送群发内容。", parse_mode=ParseMode.MARKDOWN
        )
        return True
    if flow.get("type") != "broadcast":
        return False
    target = flow["target"]
    tag = flow.get("tag")
    context.user_data.pop("flow", None)
    await _enqueue_or_run(
        update, context, target, replied=update.effective_message, tag=tag
    )
    return True


# =====================================================
# 任务执行
# =====================================================
SCHED_RE = re.compile(r"@schedule\s+(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2})")
BTN_RE = re.compile(r"@buttons\s+(\[\[.*?\]\])", re.DOTALL)


def _extract_metadata(text: str) -> tuple[str, dict]:
    """从内容里提取 @schedule / @buttons 元指令。"""
    meta: dict = {}
    m = SCHED_RE.search(text or "")
    if m:
        try:
            meta["scheduled_at"] = datetime.fromisoformat(m.group(1).replace(" ", "T"))
            text = SCHED_RE.sub("", text)
        except ValueError:
            pass
    m = BTN_RE.search(text or "")
    if m:
        try:
            meta["buttons"] = json.loads(m.group(1))
            text = BTN_RE.sub("", text)
        except Exception:
            pass
    return (text or "").strip(), meta


def _build_inline_kb(rows: list[list]) -> InlineKeyboardMarkup | None:
    if not rows:
        return None
    kb = []
    for row in rows:
        line = []
        for cell in row:
            if isinstance(cell, list) and len(cell) >= 2:
                label, payload = cell[0], cell[1]
                if str(payload).startswith(("http://", "https://", "tg://")):
                    line.append(InlineKeyboardButton(label, url=payload))
                else:
                    line.append(InlineKeyboardButton(label, callback_data=str(payload)))
        if line:
            kb.append(line)
    return InlineKeyboardMarkup(kb) if kb else None


async def _enqueue_or_run(update, context, target, text="", replied=None, tag=None):
    meta = {}
    if replied is not None and (replied.text or replied.caption):
        body = replied.text or replied.caption or ""
        cleaned, meta = _extract_metadata(body)
        if replied.text:
            replied.text = cleaned  # type: ignore[attr-defined]
        elif replied.caption is not None:
            replied._caption = cleaned  # type: ignore[attr-defined]
    elif text:
        text, meta = _extract_metadata(text)

    async with SessionLocal() as s:
        job = BroadcastJob(
            target_type=target,
            target_tag=tag,
            content=text or (replied.text or replied.caption or "[media]" if replied else ""),
            payload={"buttons": meta.get("buttons")} if meta.get("buttons") else None,
            status="pending",
            scheduled_at=meta.get("scheduled_at"),
        )
        s.add(job)
        await s.commit()
        await s.refresh(job)
        job_id = job.id

    if meta.get("scheduled_at"):
        await update.effective_message.reply_text(
            f"⏰ 已创建定时任务 #{job_id}，将于 {meta['scheduled_at']:%Y-%m-%d %H:%M} 触发"
        )
        return

    # 即时执行
    await _execute_job(context.bot, job_id, notice_chat=update.effective_chat.id, replied=replied)


async def execute_job_id(app, job_id: int) -> None:
    """供调度器调用：通过 Application 上下文执行某个 job。"""
    await _execute_job(app.bot, job_id)


async def _collect_targets(target: str, tag: str | None = None):
    user_ids: list[int] = []
    chat_ids: list[int] = []
    async with SessionLocal() as s:
        if target in ("users", "both", "tag"):
            stmt = select(User.id).where(
                User.is_blocked.is_(False), User.is_banned.is_(False)
            )
            if target == "tag" and tag:
                stmt = stmt.where(User.tags.is_not(None), User.tags.like(f"%{tag}%"))
            user_ids = list((await s.execute(stmt)).scalars().all())
        if target in ("chats", "both"):
            chat_ids = list(
                (
                    await s.execute(
                        select(Chat.id).where(Chat.is_active.is_(True))
                    )
                ).scalars().all()
            )
    return user_ids, chat_ids


async def _execute_job(bot, job_id: int, notice_chat=None, replied=None) -> None:
    async with SessionLocal() as s:
        job = await s.get(BroadcastJob, job_id)
        if not job:
            return
        target = job.target_type
        tag = job.target_tag
        content = job.content
        buttons = (job.payload or {}).get("buttons") if job.payload else None
        job.status = "running"
        job.started_at = datetime.utcnow()
        await s.commit()

    user_ids, chat_ids = await _collect_targets(target, tag)
    total = len(user_ids) + len(chat_ids)
    if total == 0:
        async with SessionLocal() as s:
            job = await s.get(BroadcastJob, job_id)
            if job:
                job.status = "done"
                job.finished_at = datetime.utcnow()
                await s.commit()
        if notice_chat:
            await bot.send_message(notice_chat, "📭 当前没有可用目标")
        return

    async with SessionLocal() as s:
        job = await s.get(BroadcastJob, job_id)
        if job:
            job.total = total
            await s.commit()

    notice = None
    if notice_chat:
        notice = await bot.send_message(
            notice_chat, f"📣 群发 #{job_id} 开始，目标 {total} 个…"
        )

    interval = settings.broadcast_interval_ms / 1000.0
    sent = failed = 0
    failed_user_ids: list[int] = []
    kb = _build_inline_kb(buttons) if buttons else None

    async def send_to(chat_id: int) -> bool:
        try:
            if replied is not None:
                await replied.copy(chat_id=chat_id, reply_markup=kb)
            else:
                await bot.send_message(chat_id=chat_id, text=content, reply_markup=kb)
            return True
        except Forbidden:
            return False
        except BadRequest as e:
            log.warning("BadRequest 群发到 %s: %s", chat_id, e)
            return False
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            return await send_to(chat_id)
        except Exception as e:  # noqa: BLE001
            log.warning("群发异常 %s: %s", chat_id, e)
            return False

    step = max(1, total // 20)
    all_targets = [("u", uid) for uid in user_ids] + [("c", cid) for cid in chat_ids]
    for idx, (kind, cid) in enumerate(all_targets, 1):
        ok = await send_to(cid)
        if ok:
            sent += 1
        else:
            failed += 1
            if kind == "u":
                failed_user_ids.append(cid)
        if notice and (idx % step == 0 or idx == total):
            try:
                await notice.edit_text(
                    f"📣 群发 #{job_id} 进行中… {idx}/{total} (✅{sent} ❌{failed})"
                )
            except Exception:
                pass
        await asyncio.sleep(interval)

    async with SessionLocal() as s:
        job = await s.get(BroadcastJob, job_id)
        if job:
            job.sent = sent
            job.failed = failed
            job.status = "done"
            job.finished_at = datetime.utcnow()
        for uid in failed_user_ids:
            u = await s.get(User, uid)
            if u:
                u.is_blocked = True
        await s.commit()

    if notice:
        try:
            await notice.edit_text(
                f"✅ 群发 #{job_id} 完成\n"
                f"总计：{total}  成功：{sent}  失败：{failed}\n"
                f"已自动屏蔽 {len(failed_user_ids)} 个无法触达的用户"
            )
        except Exception:
            pass


async def _list_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as s:
        rows = (
            await s.execute(select(BroadcastJob).order_by(BroadcastJob.id.desc()).limit(15))
        ).scalars().all()
    if not rows:
        text = "📭 暂无群发记录"
    else:
        lines = ["📜 *最近群发*\n"]
        for j in rows:
            when = (j.scheduled_at or j.created_at).strftime("%m-%d %H:%M")
            lines.append(
                f"`#{j.id}` {j.status} · {j.target_type}"
                + (f" [{j.target_tag}]" if j.target_tag else "")
                + f" · {j.sent}/{j.total} · {when}"
            )
        text = "\n".join(lines)
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=back_home()
        )
    else:
        await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
