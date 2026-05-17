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

from sqlalchemy import select
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.tl.types import (
    DocumentAttributeFilename,
    MessageMediaDocument,
    MessageMediaPhoto,
)

from .config import settings
from .database import ForwardRule, SessionLocal
from .plugins import MessageContext, build_chain

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


async def _send(client: TelegramClient, target, msg, ctx: MessageContext) -> None:
    if ctx.media_type == "text" or not msg.media:
        text = ctx.text or "(空消息)"
        await client.send_message(target, text)
        return

    if ctx.media_bytes is not None:
        f = io.BytesIO(ctx.media_bytes)
        f.name = ctx.media_filename or "media.jpg"
        await client.send_file(target, f, caption=ctx.caption or None)
        return

    # 直接转发媒体引用（不下载）
    await client.send_file(target, msg.media, caption=ctx.caption or None)


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
        need_bytes = "watermark" in (rule.plugins or {})
        ctx = await _build_ctx(self.client, msg, need_bytes)

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
        for target in _split_targets(rule.targets):
            try:
                await _send(self.client, target, msg, ctx)
                ok_targets += 1
            except FloodWaitError as e:
                log.warning("FloodWait %ss 规则 #%s", e.seconds, rule.id)
                await asyncio.sleep(e.seconds + 1)
                try:
                    await _send(self.client, target, msg, ctx)
                    ok_targets += 1
                except Exception as e2:  # noqa: BLE001
                    log.warning("规则 #%s → %s 转发失败: %s", rule.id, target, e2)
            except Exception as e:  # noqa: BLE001
                log.warning("规则 #%s → %s 转发失败: %s", rule.id, target, e)

        async with SessionLocal() as s:
            obj = await s.get(ForwardRule, rule.id)
            if obj:
                if ok_targets:
                    obj.forwarded_count += 1
                else:
                    obj.dropped_count += 1
                obj.last_message_id = max(obj.last_message_id or 0, msg.id or 0)
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
