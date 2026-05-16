"""通用工具：权限、文本处理、解析。"""
from __future__ import annotations

import functools
import re
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Optional, Tuple

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from .config import settings
from .database import SessionLocal, User


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


def admin_only(
    func: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]
) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]:
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user or not is_admin(user.id):
            if update.effective_message:
                await update.effective_message.reply_text("⛔ 仅管理员可用")
            return
        await func(update, context)

    return wrapper


async def upsert_user(update: Update) -> None:
    """记录与机器人交互过的用户。"""
    tg_user = update.effective_user
    if not tg_user or tg_user.is_bot:
        return

    async with SessionLocal() as s:
        existing = await s.get(User, tg_user.id)
        if existing:
            existing.username = tg_user.username
            existing.first_name = tg_user.first_name
            existing.last_name = tg_user.last_name
            existing.language = tg_user.language_code
            existing.last_seen = datetime.utcnow()
        else:
            s.add(
                User(
                    id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                    last_name=tg_user.last_name,
                    language=tg_user.language_code,
                    is_admin=is_admin(tg_user.id),
                )
            )
        await s.commit()


# ---------- 金额 / 文本解析 ----------

_AMOUNT_RE = re.compile(r"^([+-]?\d+(?:\.\d+)?)(.*)$", re.DOTALL)


def parse_amount_note(text: str) -> Tuple[Optional[float], str, str]:
    """
    解析记账输入：
      `120 餐饮 午餐`   -> (120, 餐饮, 午餐)
      `-50 打车`        -> (-50, 打车, "")
      `200 工资 5月`    -> (200, 工资, 5月)
    """
    parts = text.strip().split(maxsplit=2)
    if not parts:
        return None, "", ""
    m = _AMOUNT_RE.match(parts[0])
    if not m:
        return None, "", ""
    try:
        amount = float(m.group(1))
    except ValueError:
        return None, "", ""
    category = parts[1] if len(parts) > 1 else "其他"
    note = parts[2] if len(parts) > 2 else ""
    return amount, category, note


def display_name(user) -> str:
    if user is None:
        return "未知"
    name = " ".join(filter(None, [user.first_name, user.last_name])) or ""
    if user.username:
        return f"{name} (@{user.username})" if name else f"@{user.username}"
    return name or f"id:{user.id}"


def month_range(now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    now = now or datetime.utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        nxt = start.replace(year=start.year + 1, month=1)
    else:
        nxt = start.replace(month=start.month + 1)
    return start, nxt


def today_range(now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    now = now or datetime.utcnow()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]
