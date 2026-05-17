"""
User-bot 搬运执行器：Telethon。

特性：
- 插件链（filter/replace/format/caption/watermark/media/length/sender）
- 多目标（一对多）
- 历史回填（past mode 一次性 / 按区间）
- 断点续传（last_message_id）
"""
from __future__ import annotations

import asyncio
import io
import logging
from typing import List, Optional

from sqlalchemy import delete, select
from telethon import Button, TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.tl.types import (
    DocumentAttributeFilename,
    MessageMediaDocument,
    MessageMediaPhoto,
)

from .config import settings
from .database import ForwardedMapping, ForwardRule, SessionLocal
from .plugins import MessageContext, build_chain

# 持有 python-telegram-bot 的 Application 引用（main.py 启动后注入）
_bot_app = None


def set_bot_app(app) -> None:
    global _bot_app
    _bot_app = app

log = logging.getLogger(__name__)


def _parse_chat(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None
    if raw.startswith("@"):
        return raw
    try:
        return int(raw)
    except ValueError:
        return raw


def _split_targets(raw: str) -> List:
    return [t for t in (_parse_chat(p) for p in (raw or "").split(",")) if t]


async def _load_rules(mode: Optional[str] = "live") -> list[ForwardRule]:
    async with SessionLocal() as s:
        stmt = select(ForwardRule).where(ForwardRule.enabled.is_(True))
        if mode:
            stmt = stmt.where(ForwardRule.mode == mode)
        return list((await s.execute(stmt)).scalars().all())


def _detect_media_type(msg) -> str:
    media = msg.media
    if not media:
        return "text"
    if isinstance(media, MessageMediaPhoto):
        return "photo"
    if isinstance(media, MessageMediaDocument):
        doc = media.document
        mime = (doc.mime_type or "").lower()
        if mime.startswith("video/"):
            return "video"
        if mime.startswith("audio/"):
            return "audio"
        if mime.startswith("image/"):
            return "photo"
        for a in (doc.attributes or []):
            if isinstance(a, DocumentAttributeFilename):
                return "document"
        return "document"
    return "other"


async def _build_ctx(client: TelegramClient, msg, need_bytes: bool) -> MessageContext:
    ctx = MessageContext()
    ctx.text = msg.message or ""
    ctx.caption = msg.message or ""
    ctx.media_type = _detect_media_type(msg)
    ctx.chat_id = msg.chat_id
    ctx.message_id = msg.id
    try:
        sender = await msg.get_sender()
        if sender:
            ctx.sender_id = getattr(sender, "id", None)
            ctx.sender_username = getattr(sender, "username", None)
    except Exception:  # noqa: BLE001
        pass
    chat = msg.chat
    if chat is not None:
        ctx.chat_username = getattr(chat, "username", None)

    if need_bytes and ctx.media_type == "photo":
        try:
            buf = io.BytesIO()
            await client.download_media(msg, file=buf)
            ctx.media_bytes = buf.getvalue()
        except Exception as e:  # noqa: BLE001
            log.warning("下载图片失败：%s", e)
    return ctx


def _build_telethon_buttons(rows):
    """把 [[{label,url}, ...], ...] 转成 Telethon Buttons。"""
    if not rows:
        return None
    out = []
    for row in rows:
        line = []
        for b in row:
            label = b.get("label")
            url = b.get("url")
            if label and url:
                line.append(Button.url(label, url))
        if line:
            out.append(line)
    return out or None


async def _send_via_user(
    client: TelegramClient, target, msg, ctx: MessageContext, target_topic=None
) -> Optional[int]:
    """user-bot 发送。返回新消息 id。"""
    buttons = _build_telethon_buttons(ctx.extra.get("buttons"))
    extra_kw = {}
    if target_topic:
        extra_kw["reply_to"] = int(target_topic)
    if buttons:
        extra_kw["buttons"] = buttons

    if ctx.media_type == "text" or not msg.media:
        text = ctx.text or "(空消息)"
        sent = await client.send_message(target, text, **extra_kw)
    elif ctx.media_bytes is not None:
        f = io.BytesIO(ctx.media_bytes)
        f.name = ctx.media_filename or "media.jpg"
        sent = await client.send_file(target, f, caption=ctx.caption or None, **extra_kw)
    else:
        sent = await client.send_file(target, msg.media, caption=ctx.caption or None, **extra_kw)
    return getattr(sent, "id", None)


async def _send_via_bot(
    target, msg, ctx: MessageContext, target_topic=None
) -> Optional[int]:
    """python-telegram-bot 发送（同步过的目标必须是 bot 也在里面的群/频道）。"""
    if not _bot_app:
        log.warning("sender=bot 但 bot Application 未注入，回退 user 模式")
        return None
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    bot = _bot_app.bot
    kb = None
    rows = ctx.extra.get("buttons")
    if rows:
        kb_rows = []
        for row in rows:
            line = [
                InlineKeyboardButton(b["label"], url=b["url"])
                for b in row if b.get("label") and b.get("url")
            ]
            if line:
                kb_rows.append(line)
        if kb_rows:
            kb = InlineKeyboardMarkup(kb_rows)
    extra = {}
    if target_topic:
        extra["message_thread_id"] = int(target_topic)
    try:
        if ctx.media_type == "photo" and ctx.media_bytes:
            res = await bot.send_photo(
                chat_id=target, photo=ctx.media_bytes,
                caption=ctx.caption or None, reply_markup=kb, **extra,
            )
        elif ctx.media_type == "text":
            res = await bot.send_message(
                chat_id=target, text=ctx.text or "(空消息)",
                reply_markup=kb, **extra,
            )
        else:
            # bot 发文档/视频要 file_id 或上传，复杂场景仅文字
            res = await bot.send_message(
                chat_id=target, text=ctx.caption or ctx.text or "(媒体)",
                reply_markup=kb, **extra,
            )
        return res.message_id
    except Exception as e:  # noqa: BLE001
        log.warning("bot 发送到 %s 失败: %s", target, e)
        return None


def _get_topic_id(msg) -> Optional[int]:
    """提取 Telethon 消息所属 forum topic id（如果是 topic 群里的消息）。"""
    try:
        rt = getattr(msg, "reply_to", None)
        if rt and getattr(rt, "forum_topic", False):
            # 顶层 topic 消息：top_msg_id = reply_to_msg_id
            return getattr(rt, "reply_to_top_id", None) or getattr(rt, "reply_to_msg_id", None)
    except Exception:
        pass
    return None


def _extract_msg_buttons(msg) -> list:
    """从 Telethon 消息提取按钮 -> [[{label,url}],...]"""
    out = []
    try:
        if not msg.buttons:
            return out
        for row in msg.buttons:
            r = []
            for b in row:
                lab = getattr(b, "text", None) or ""
                url = getattr(b, "url", None) or ""
                if lab:
                    r.append({"label": lab, "url": url})
            if r:
                out.append(r)
    except Exception:
        pass
    return out


def _rule_matches_chat(rule: ForwardRule, chat_id: int, chat_username: Optional[str]) -> bool:
    src = _parse_chat(rule.source_chat)
    if isinstance(src, int):
        return src == chat_id
    if isinstance(src, str) and chat_username:
        return src.lstrip("@").lower() == chat_username.lower()
    return False


class ForwardManager:
    def __init__(self) -> None:
        self.client: Optional[TelegramClient] = None
        self._reload_event = asyncio.Event()
        self._rules: list[ForwardRule] = []

    async def _process_one(self, rule: ForwardRule, msg) -> None:
        # Topic 过滤
        if rule.source_topic:
            top_id = _get_topic_id(msg)
            if top_id != int(rule.source_topic):
                return

        need_bytes = "watermark" in (rule.plugins or {})
        ctx = await _build_ctx(self.client, msg, need_bytes)
        ctx.extra["rule_id"] = rule.id
        ctx.extra["source_buttons"] = _extract_msg_buttons(msg)

        chain = build_chain(rule.plugins)
        allow = await chain.run(ctx)
        if not allow:
            async with SessionLocal() as s:
                obj = await s.get(ForwardRule, rule.id)
                if obj:
                    obj.dropped_count += 1
                    await s.commit()
            return

        ok_targets = 0
        mappings: list[tuple[str, int, str]] = []
        sender = rule.sender or "user"

        async def _send_to(target):
            nonlocal ok_targets
            try:
                if sender == "bot" and _bot_app:
                    new_id = await _send_via_bot(target, msg, ctx, rule.target_topic)
                    used = "bot"
                else:
                    new_id = await _send_via_user(
                        self.client, target, msg, ctx, rule.target_topic
                    )
                    used = "user"
                if new_id:
                    ok_targets += 1
                    mappings.append((str(target), new_id, used))
            except FloodWaitError as e:
                log.warning("FloodWait %ss 规则 #%s", e.seconds, rule.id)
                await asyncio.sleep(e.seconds + 1)
                # 简化：FloodWait 后不再重试，跳过
            except Exception as e:  # noqa: BLE001
                log.warning("规则 #%s → %s 转发失败: %s", rule.id, target, e)

        for target in _split_targets(rule.targets):
            await _send_to(target)

        async with SessionLocal() as s:
            obj = await s.get(ForwardRule, rule.id)
            if obj:
                if ok_targets:
                    obj.forwarded_count += 1
                else:
                    obj.dropped_count += 1
                obj.last_message_id = max(obj.last_message_id or 0, msg.id or 0)
            # 保存映射用于编辑/删除同步
            if mappings and (rule.sync_edits or rule.sync_deletes):
                for dst, mid, used in mappings:
                    s.add(
                        ForwardedMapping(
                            rule_id=rule.id,
                            src_chat_id=msg.chat_id,
                            src_msg_id=msg.id,
                            dst_chat=dst,
                            dst_msg_id=mid,
                            sent_by=used,
                        )
                    )
            await s.commit()

    async def _on_message_edited(self, event):
        """源消息编辑 -> 同步编辑所有 dst。"""
        msg = event.message
        async with SessionLocal() as s:
            stmt = select(ForwardedMapping, ForwardRule).join(
                ForwardRule, ForwardRule.id == ForwardedMapping.rule_id
            ).where(
                ForwardedMapping.src_chat_id == msg.chat_id,
                ForwardedMapping.src_msg_id == msg.id,
                ForwardRule.sync_edits.is_(True),
            )
            rows = (await s.execute(stmt)).all()
        if not rows:
            return
        for mp, rule in rows:
            ctx = await _build_ctx(self.client, msg, False)
            ctx.extra["rule_id"] = rule.id
            chain = build_chain(rule.plugins or {})
            if not await chain.run(ctx):
                continue
            new_text = ctx.text or ctx.caption
            try:
                target = _parse_chat(mp.dst_chat)
                if mp.sent_by == "bot" and _bot_app:
                    try:
                        await _bot_app.bot.edit_message_text(
                            chat_id=target, message_id=mp.dst_msg_id, text=new_text
                        )
                    except Exception:
                        await _bot_app.bot.edit_message_caption(
                            chat_id=target, message_id=mp.dst_msg_id, caption=new_text
                        )
                else:
                    await self.client.edit_message(target, mp.dst_msg_id, new_text)
                log.info("✏️  同步编辑 rule#%s src=%s dst=%s/%s",
                         rule.id, msg.id, mp.dst_chat, mp.dst_msg_id)
            except Exception as e:  # noqa: BLE001
                log.warning("编辑同步失败: %s", e)

    async def _on_message_deleted(self, event):
        """源消息删除 -> 同步删除所有 dst。"""
        deleted_ids = list(event.deleted_ids or [])
        chat_id = event.chat_id
        if not chat_id or not deleted_ids:
            return
        async with SessionLocal() as s:
            stmt = select(ForwardedMapping, ForwardRule).join(
                ForwardRule, ForwardRule.id == ForwardedMapping.rule_id
            ).where(
                ForwardedMapping.src_chat_id == chat_id,
                ForwardedMapping.src_msg_id.in_(deleted_ids),
                ForwardRule.sync_deletes.is_(True),
            )
            rows = (await s.execute(stmt)).all()
            if not rows:
                return
            for mp, rule in rows:
                try:
                    target = _parse_chat(mp.dst_chat)
                    if mp.sent_by == "bot" and _bot_app:
                        await _bot_app.bot.delete_message(chat_id=target, message_id=mp.dst_msg_id)
                    else:
                        await self.client.delete_messages(target, mp.dst_msg_id)
                    log.info("🗑  同步删除 rule#%s src=%s dst=%s/%s",
                             rule.id, mp.src_msg_id, mp.dst_chat, mp.dst_msg_id)
                except Exception as e:  # noqa: BLE001
                    log.warning("删除同步失败: %s", e)
            # 清理映射
            await s.execute(
                delete(ForwardedMapping).where(
                    ForwardedMapping.src_chat_id == chat_id,
                    ForwardedMapping.src_msg_id.in_(deleted_ids),
                )
            )
            await s.commit()

    async def _on_message(self, event):
        msg = event.message
        chat_username = getattr(event.chat, "username", None) if event.chat else None
        for rule in self._rules:
            if not _rule_matches_chat(rule, event.chat_id, chat_username):
                continue
            try:
                await self._process_one(rule, msg)
            except Exception:  # noqa: BLE001
                log.exception("处理规则 #%s 异常", rule.id)

    async def _refresh_loop(self) -> None:
        while True:
            self._rules = await _load_rules("live")
            log.info("user-bot: 加载 %d 条实时规则", len(self._rules))
            try:
                await asyncio.wait_for(self._reload_event.wait(), timeout=60)
                self._reload_event.clear()
            except asyncio.TimeoutError:
                pass

    def request_reload(self) -> None:
        self._reload_event.set()

    # ---- 历史回填 ----
    async def backfill(self, rule_id: int, limit: int = 200, since_id: Optional[int] = None) -> dict:
        """把指定规则的源里历史 N 条按规则处理后发到目标。"""
        if not self.client:
            return {"ok": False, "err": "user-bot 未启动"}
        async with SessionLocal() as s:
            rule = await s.get(ForwardRule, rule_id)
        if not rule:
            return {"ok": False, "err": "规则不存在"}

        src = _parse_chat(rule.source_chat)
        sent = dropped = 0
        kwargs = {"limit": limit}
        if since_id:
            kwargs["min_id"] = since_id
        async for msg in self.client.iter_messages(src, **kwargs):
            try:
                before = rule.forwarded_count
                await self._process_one(rule, msg)
                async with SessionLocal() as s2:
                    fresh = await s2.get(ForwardRule, rule.id)
                    if fresh and fresh.forwarded_count > before:
                        sent += 1
                    else:
                        dropped += 1
                await asyncio.sleep(0.5)  # 防 FloodWait
            except Exception as e:  # noqa: BLE001
                log.warning("backfill 异常: %s", e)
        return {"ok": True, "sent": sent, "dropped": dropped}

    async def _run_once(self) -> None:
        client = TelegramClient(
            str(settings.session_path),
            settings.api_id,
            settings.api_hash,
        )
        self.client = client
        log.info("user-bot 登录中…")
        await client.start(phone=settings.phone, password=settings.tg_password or None)
        me = await client.get_me()
        log.info("user-bot 登录成功：%s", getattr(me, "username", me.id))
        client.add_event_handler(self._on_message, events.NewMessage())
        client.add_event_handler(self._on_message_edited, events.MessageEdited())
        client.add_event_handler(self._on_message_deleted, events.MessageDeleted())
        try:
            await asyncio.gather(
                self._refresh_loop(),
                client.run_until_disconnected(),
            )
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
            self.client = None

    async def run(self) -> None:
        """指数退避自动重连：1s → 2s → 4s … 上限 5min。"""
        if not settings.userbot_enabled:
            log.warning("user-bot 未启用（缺 TG_API_ID/HASH/PHONE），搬运功能跳过。")
            return

        backoff = 1
        while True:
            try:
                await self._run_once()
                # 正常 disconnect（如 SIGTERM）
                log.info("user-bot 主动断开，停止重连循环")
                return
            except asyncio.CancelledError:
                log.info("user-bot 任务被取消")
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("user-bot 异常断线: %s；%ds 后重连", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 300)


manager = ForwardManager()


async def start_userbot() -> None:
    await manager.run()
