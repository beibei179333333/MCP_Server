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


# =============================================================
# 分页
# =============================================================
def paginate(items, page: int, per_page: int = 20) -> tuple[list, int, int]:
    """返回 (本页数据, 当前页 1-based, 总页数)。page 越界自动收敛。"""
    total = len(items)
    if total == 0:
        return [], 1, 1
    pages = (total + per_page - 1) // per_page
    page = max(1, min(page, pages))
    start = (page - 1) * per_page
    return items[start : start + per_page], page, pages


def pager_keyboard(prefix: str, page: int, pages: int, extra: list | None = None):
    """生成 ‹ 1/3 › 翻页键盘，回调 prefix:<page>。"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    row: list = []
    if page > 1:
        row.append(InlineKeyboardButton("‹ 上一页", callback_data=f"{prefix}:{page - 1}"))
    row.append(InlineKeyboardButton(f"{page}/{pages}", callback_data=f"{prefix}:{page}"))
    if page < pages:
        row.append(InlineKeyboardButton("下一页 ›", callback_data=f"{prefix}:{page + 1}"))
    rows = [row] if row else []
    if extra:
        rows.extend(extra)
    return InlineKeyboardMarkup(rows)


# =============================================================
# 文本工具
# =============================================================
MD_ESCAPE_RE = None  # 懒加载


def md_escape(text: str) -> str:
    """转义 Telegram MarkdownV1 特殊字符。"""
    return (text or "").replace("*", "\\*").replace("_", "\\_").replace("`", "\\`").replace("[", "\\[")


def short(text: str, length: int = 40) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= length else text[:length] + "…"


def fmt_time(dt) -> str:
    if not dt:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M")


def fmt_size(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.1f}{unit}"
        num /= 1024
    return f"{num:.1f}TB"

