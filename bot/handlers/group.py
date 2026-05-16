"""群组功能：欢迎语 / 验证码 / 反链接反垃圾。"""
from __future__ import annotations

import logging
import random
import re
from datetime import datetime, timedelta

from sqlalchemy import select
from telegram import (
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

from ..config import settings
from ..database import CaptchaSession, GroupSetting, SessionLocal
from ..utils import is_admin

log = logging.getLogger(__name__)

URL_RE = re.compile(r"https?://\S+")
INV_RE = re.compile(r"t\.me/\S+")
MENTION_RE = re.compile(r"@\w{4,32}")


# =============================================================
# 设置访问 / 命令
# =============================================================
async def _get_settings(chat_id: int) -> GroupSetting:
    async with SessionLocal() as s:
        gs = await s.get(GroupSetting, chat_id)
        if not gs:
            gs = GroupSetting(chat_id=chat_id, captcha_timeout=settings.captcha_timeout)
            s.add(gs)
            await s.commit()
            await s.refresh(gs)
    return gs


async def _is_group_admin(update: Update) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return False
    if is_admin(user.id):
        return True
    try:
        m = await chat.get_member(user.id)
        return m.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


async def welcome_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/welcome 欢迎文本"""
    if not await _is_group_admin(update):
        await update.effective_message.reply_text("⛔ 仅群管理员")
        return
    raw = update.effective_message.text or ""
    body = raw.split(maxsplit=1)
    if len(body) < 2:
        await update.effective_message.reply_text(
            "用法：`/welcome 欢迎 {name}，请阅读群规 …`\n占位符：`{name}` `{username}` `{chat}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    async with SessionLocal() as s:
        gs = await s.get(GroupSetting, update.effective_chat.id) or GroupSetting(
            chat_id=update.effective_chat.id
        )
        gs.welcome_text = body[1]
        gs.welcome_enabled = True
        s.add(gs)
        await s.commit()
    await update.effective_message.reply_text("✅ 欢迎语已更新")


async def welcome_off(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_group_admin(update):
        await update.effective_message.reply_text("⛔ 仅群管理员")
        return
    async with SessionLocal() as s:
        gs = await s.get(GroupSetting, update.effective_chat.id)
        if gs:
            gs.welcome_enabled = False
            await s.commit()
    await update.effective_message.reply_text("🔕 已关闭欢迎语")


async def captcha_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_group_admin(update):
        await update.effective_message.reply_text("⛔ 仅群管理员")
        return
    async with SessionLocal() as s:
        gs = await s.get(GroupSetting, update.effective_chat.id)
        if not gs:
            gs = GroupSetting(chat_id=update.effective_chat.id)
            s.add(gs)
        gs.captcha_enabled = not gs.captcha_enabled
        await s.commit()
        state = "开启 🛡" if gs.captcha_enabled else "关闭 🚫"
    await update.effective_message.reply_text(f"入群验证：{state}")


async def antispam_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_group_admin(update):
        await update.effective_message.reply_text("⛔ 仅群管理员")
        return
    async with SessionLocal() as s:
        gs = await s.get(GroupSetting, update.effective_chat.id)
        if not gs:
            gs = GroupSetting(chat_id=update.effective_chat.id)
            s.add(gs)
        gs.anti_spam_enabled = not gs.anti_spam_enabled
        await s.commit()
        state = "开启 🛡" if gs.anti_spam_enabled else "关闭 🚫"
    await update.effective_message.reply_text(f"反垃圾：{state}")


# =============================================================
# 新成员事件
# =============================================================
async def on_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """chat_member 事件：成员状态变化（join / leave / kicked）。"""
    cm = update.chat_member
    if not cm:
        return
    chat = cm.chat
    new_status = cm.new_chat_member.status
    old_status = cm.old_chat_member.status
    user = cm.new_chat_member.user
    if user.is_bot:
        return

    gs = await _get_settings(chat.id)

    is_joining = (
        old_status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED)
        and new_status == ChatMemberStatus.MEMBER
    )
    is_leaving = (
        old_status == ChatMemberStatus.MEMBER
        and new_status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED)
    )

    if is_joining:
        if gs.captcha_enabled:
            await _start_captcha(context, chat, user, gs)
        elif gs.welcome_enabled:
            await _send_welcome(context, chat, user, gs)
    elif is_leaving and gs.farewell_enabled and gs.farewell_text:
        try:
            await context.bot.send_message(
                chat.id, _render(gs.farewell_text, user, chat)
            )
        except Exception:
            pass


def _render(template: str, user, chat) -> str:
    name = user.full_name or user.first_name or "新朋友"
    return (
        (template or "")
        .replace("{name}", name)
        .replace("{username}", f"@{user.username}" if user.username else name)
        .replace("{chat}", chat.title or "本群")
    )


# =============================================================
# 验证码
# =============================================================
async def _start_captcha(context, chat, user, gs: GroupSetting) -> None:
    """禁言新成员 + 发验证消息。"""
    try:
        await context.bot.restrict_chat_member(
            chat.id, user.id, ChatPermissions(can_send_messages=False)
        )
    except (BadRequest, Forbidden):
        return  # 没有禁言权限就放过

    expires = datetime.utcnow() + timedelta(seconds=gs.captcha_timeout)

    if gs.captcha_type == "math":
        a, b = random.randint(2, 9), random.randint(2, 9)
        answer = str(a + b)
        text = (
            f"👋 [{user.first_name}](tg://user?id={user.id})，请在 "
            f"{gs.captcha_timeout}s 内回答：\n*{a} + {b} = ?*\n"
            f"直接发数字答案即可。错误或超时将被踢出。"
        )
        kb = None
    else:
        answer = str(random.randint(1000, 9999))
        text = (
            f"👋 [{user.first_name}](tg://user?id={user.id})，请在 "
            f"{gs.captcha_timeout}s 内点击下方 *我是人类* 按钮完成验证。"
        )
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ 我是人类", callback_data=f"cap:{user.id}:{answer}")]]
        )

    msg = await context.bot.send_message(
        chat.id, text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb
    )

    async with SessionLocal() as s:
        # 删除旧的同 chat+user 记录
        existing = (
            await s.execute(
                select(CaptchaSession).where(
                    CaptchaSession.chat_id == chat.id,
                    CaptchaSession.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            await s.delete(existing)
        s.add(
            CaptchaSession(
                chat_id=chat.id,
                user_id=user.id,
                answer=answer,
                expires_at=expires,
                message_id=msg.message_id,
            )
        )
        await s.commit()


async def _send_welcome(context, chat, user, gs: GroupSetting) -> None:
    text = _render(
        gs.welcome_text or "👋 欢迎 {name} 加入 {chat}！",
        user,
        chat,
    )
    try:
        await context.bot.send_message(chat.id, text)
    except Exception:
        pass


async def captcha_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    parts = query.data.split(":")
    if len(parts) != 3:
        return
    _, uid_s, expected = parts
    if str(query.from_user.id) != uid_s:
        await query.answer("这不是给你的验证哦", show_alert=True)
        return
    async with SessionLocal() as s:
        sess = (
            await s.execute(
                select(CaptchaSession).where(
                    CaptchaSession.chat_id == query.message.chat_id,
                    CaptchaSession.user_id == query.from_user.id,
                )
            )
        ).scalar_one_or_none()
        if not sess:
            await query.answer("验证已失效", show_alert=True)
            return
        if sess.answer != expected:
            await query.answer("校验失败", show_alert=True)
            return
        await s.delete(sess)
        await s.commit()
    try:
        await context.bot.restrict_chat_member(
            query.message.chat_id,
            query.from_user.id,
            ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
    except Exception:  # noqa: BLE001
        pass
    try:
        await query.message.delete()
    except Exception:
        pass
    gs = await _get_settings(query.message.chat_id)
    if gs.welcome_enabled:
        await _send_welcome(context, query.message.chat, query.from_user, gs)
    await query.answer("✅ 验证通过")


async def captcha_text_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """math 验证：用户回复纯数字时检查。"""
    msg = update.effective_message
    if not msg or not msg.text:
        return False
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    text = msg.text.strip()
    if not text.isdigit():
        return False
    async with SessionLocal() as s:
        sess = (
            await s.execute(
                select(CaptchaSession).where(
                    CaptchaSession.chat_id == chat_id,
                    CaptchaSession.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if not sess:
            return False
        if sess.answer != text:
            return True  # 视为处理过，避免被其他 handler 处理为入账
        await s.delete(sess)
        await s.commit()
    try:
        await context.bot.restrict_chat_member(
            chat_id, user_id,
            ChatPermissions(
                can_send_messages=True, can_send_audios=True, can_send_documents=True,
                can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
                can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
    except Exception:
        pass
    if sess.message_id:
        try:
            await context.bot.delete_message(chat_id, sess.message_id)
        except Exception:
            pass
    gs = await _get_settings(chat_id)
    if gs.welcome_enabled:
        await _send_welcome(context, update.effective_chat, update.effective_user, gs)
    return True


# =============================================================
# 反垃圾
# =============================================================
async def antispam_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """命中则删除并返回 True。"""
    msg = update.effective_message
    if not msg:
        return False
    chat = update.effective_chat
    if chat.type == "private":
        return False
    gs = await _get_settings(chat.id)
    if not gs.anti_spam_enabled:
        return False
    # 不处理本群管理员
    try:
        m = await chat.get_member(update.effective_user.id)
        if m.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
            return False
    except Exception:
        pass
    text = msg.text or msg.caption or ""
    hit_link = bool(URL_RE.search(text) or INV_RE.search(text))
    hit_mention = bool(MENTION_RE.search(text))
    if (gs.block_links and hit_link) or (gs.block_forward and msg.forward_origin):
        try:
            await msg.delete()
            return True
        except Exception:
            pass
    if hit_link and hit_mention and len(text) > 200:  # 启发式：链接+@+长文 ≈ 广告
        try:
            await msg.delete()
            return True
        except Exception:
            pass
    return False
