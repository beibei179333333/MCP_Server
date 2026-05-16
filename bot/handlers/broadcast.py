"""群发：用户 / 群组 / 全部，含节流与失败统计。"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Iterable

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import Forbidden, BadRequest, RetryAfter
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
                InlineKeyboardButton("👥 发给所有用户", callback_data="bc:target:users"),
                InlineKeyboardButton("💬 发给所有群组", callback_data="bc:target:chats"),
            ],
            [InlineKeyboardButton("🌐 全部（用户+群）", callback_data="bc:target:both")],
            [InlineKeyboardButton("« 返回", callback_data="menu:home")],
        ]
    )


async def open_broadcast_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📣 *群发中心*\n\n"
        "选择目标后，发送任意消息（文本/图片/文件）将作为群发内容。\n"
        "也可直接使用：\n"
        "  `/broadcast users 内容`\n"
        "  `/broadcast chats 内容`\n"
        "  `/broadcast both 内容`\n"
        "或回复一条消息后执行 `/broadcast users` 转发该消息。"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=_panel_keyboard()
        )
    else:
        await update.effective_message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=_panel_keyboard()
        )


@admin_only
async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await open_broadcast_panel(update, context)
        return
    target = context.args[0].lower()
    if target not in ("users", "chats", "both"):
        await update.effective_message.reply_text(
            "用法：`/broadcast <users|chats|both> 内容`", parse_mode=ParseMode.MARKDOWN
        )
        return

    text = " ".join(context.args[1:]).strip()
    replied = update.effective_message.reply_to_message
    if not text and not replied:
        await update.effective_message.reply_text("⚠️ 请提供内容或回复一条消息")
        return

    await _run_broadcast(update, context, target, text=text, replied=replied)


async def broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        await query.edit_message_text("⛔ 仅管理员可用", reply_markup=back_home())
        return
    parts = query.data.split(":")
    if len(parts) >= 3 and parts[1] == "target":
        target = parts[2]
        context.user_data["flow"] = {"type": "broadcast", "target": target}
        await query.edit_message_text(
            f"📤 已选择目标：*{target}*\n请发送要群发的内容（任意消息类型）。\n发送 /cancel 取消。",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await open_broadcast_panel(update, context)


async def handle_broadcast_content(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """如果用户在 broadcast flow 中，发送的消息将作为内容。"""
    flow = context.user_data.get("flow")
    if not flow or flow.get("type") != "broadcast":
        return False
    target = flow["target"]
    context.user_data.pop("flow", None)
    await _run_broadcast(update, context, target, replied=update.effective_message)
    return True


async def _collect_targets(target: str) -> tuple[list[int], list[int]]:
    user_ids: list[int] = []
    chat_ids: list[int] = []
    async with SessionLocal() as s:
        if target in ("users", "both"):
            rows = (
                await s.execute(
                    select(User.id).where(User.is_blocked.is_(False))
                )
            ).scalars().all()
            user_ids = list(rows)
        if target in ("chats", "both"):
            rows = (
                await s.execute(
                    select(Chat.id).where(Chat.is_active.is_(True))
                )
            ).scalars().all()
            chat_ids = list(rows)
    return user_ids, chat_ids


async def _run_broadcast(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    target: str,
    text: str = "",
    replied=None,
) -> None:
    user_ids, chat_ids = await _collect_targets(target)
    total = len(user_ids) + len(chat_ids)
    if total == 0:
        await update.effective_message.reply_text("📭 当前没有可用目标")
        return

    async with SessionLocal() as s:
        job = BroadcastJob(
            target_type=target,
            content=text or (replied.text or replied.caption or "[media]" if replied else ""),
            total=total,
            started_at=datetime.utcnow(),
        )
        s.add(job)
        await s.commit()
        await s.refresh(job)
        job_id = job.id

    notice = await update.effective_message.reply_text(
        f"📣 开始群发任务 #{job_id}\n目标 {total} 个，进度 0/{total}…"
    )

    interval = settings.broadcast_interval_ms / 1000.0
    sent = 0
    failed = 0
    failed_user_ids: list[int] = []

    async def send_to(chat_id: int) -> bool:
        try:
            if replied is not None:
                await replied.copy(chat_id=chat_id)
            else:
                await context.bot.send_message(chat_id=chat_id, text=text)
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

    progress_step = max(1, total // 20)

    for idx, uid in enumerate(user_ids, 1):
        ok = await send_to(uid)
        if ok:
            sent += 1
        else:
            failed += 1
            failed_user_ids.append(uid)
        if (idx % progress_step) == 0 or idx == len(user_ids):
            try:
                await notice.edit_text(
                    f"📣 群发 #{job_id} 进行中… {sent + failed}/{total} "
                    f"(✅{sent} ❌{failed})"
                )
            except Exception:
                pass
        await asyncio.sleep(interval)

    for idx, cid in enumerate(chat_ids, 1):
        ok = await send_to(cid)
        if ok:
            sent += 1
        else:
            failed += 1
        if (idx % progress_step) == 0 or idx == len(chat_ids):
            try:
                await notice.edit_text(
                    f"📣 群发 #{job_id} 进行中… {sent + failed}/{total} "
                    f"(✅{sent} ❌{failed})"
                )
            except Exception:
                pass
        await asyncio.sleep(interval)

    async with SessionLocal() as s:
        job = await s.get(BroadcastJob, job_id)
        if job:
            job.sent = sent
            job.failed = failed
            job.finished_at = datetime.utcnow()

        # 标记拉黑机器人的用户
        if failed_user_ids:
            for uid in failed_user_ids:
                u = await s.get(User, uid)
                if u:
                    u.is_blocked = True
        await s.commit()

    await notice.edit_text(
        f"✅ 群发 #{job_id} 完成\n"
        f"总计：{total}  成功：{sent}  失败：{failed}\n"
        f"已自动标记 {len(failed_user_ids)} 个无法触达的用户。"
    )
