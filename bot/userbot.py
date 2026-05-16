"""
user-bot 搬运执行：用 Telethon 监听源频道/群组并按规则转发。

Bot API 无法接收 *非订阅* 频道的消息，因此搬运需要用 user-bot 账号。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

from .config import settings
from .database import ForwardRule, SessionLocal

log = logging.getLogger(__name__)


def _parse_chat(raw: str):
    raw = raw.strip()
    if raw.startswith("@"):
        return raw
    try:
        return int(raw)
    except ValueError:
        return raw


async def _load_rules() -> list[ForwardRule]:
    async with SessionLocal() as s:
        stmt = select(ForwardRule).where(ForwardRule.enabled.is_(True))
        return list((await s.execute(stmt)).scalars().all())


def _match_rule(rule: ForwardRule, text: str) -> bool:
    text_low = (text or "").lower()
    if rule.blacklist:
        for w in (w.strip().lower() for w in rule.blacklist.split(",") if w.strip()):
            if w in text_low:
                return False
    if rule.keywords:
        words = [w.strip().lower() for w in rule.keywords.split(",") if w.strip()]
        if words and not any(w in text_low for w in words):
            return False
    return True


def _transform(rule: ForwardRule, text: str) -> str:
    if not text:
        return text
    if rule.replace_from:
        text = text.replace(rule.replace_from, rule.replace_to or "")
    if rule.strip_links:
        import re
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"@\w+", "", text)
    return text


class ForwardManager:
    def __init__(self) -> None:
        self.client: Optional[TelegramClient] = None
        self._reload_event = asyncio.Event()
        self._rules_cache: list[ForwardRule] = []

    async def _on_message(self, event):
        chat_id = event.chat_id
        text = event.message.message or ""

        triggered: list[ForwardRule] = []
        for rule in self._rules_cache:
            src = _parse_chat(rule.source_chat)
            matches_chat = False
            if isinstance(src, int):
                matches_chat = src == chat_id
            else:  # @username
                if event.chat and getattr(event.chat, "username", None):
                    matches_chat = ("@" + event.chat.username.lower()) == src.lower()
            if not matches_chat:
                continue
            if not _match_rule(rule, text):
                continue
            triggered.append(rule)

        for rule in triggered:
            target = _parse_chat(rule.target_chat)
            new_text = _transform(rule, text)
            try:
                if event.message.media and not new_text:
                    await self.client.send_file(target, event.message.media)
                elif event.message.media:
                    await self.client.send_file(target, event.message.media, caption=new_text)
                else:
                    await self.client.send_message(target, new_text or "(无文本)")
                async with SessionLocal() as s:
                    obj = await s.get(ForwardRule, rule.id)
                    if obj:
                        obj.forwarded_count += 1
                        await s.commit()
                log.info("规则 #%s 转发成功", rule.id)
            except FloodWaitError as e:
                log.warning("FloodWait %ss，规则 #%s", e.seconds, rule.id)
                await asyncio.sleep(e.seconds + 1)
            except Exception as e:  # noqa: BLE001
                log.warning("规则 #%s 转发失败：%s", rule.id, e)

    async def _refresh_loop(self) -> None:
        while True:
            self._rules_cache = await _load_rules()
            log.info("已加载 %d 条搬运规则", len(self._rules_cache))
            try:
                await asyncio.wait_for(self._reload_event.wait(), timeout=60)
                self._reload_event.clear()
            except asyncio.TimeoutError:
                pass

    def request_reload(self) -> None:
        self._reload_event.set()

    async def run(self) -> None:
        if not settings.userbot_enabled:
            log.warning("user-bot 未启用（缺 TG_API_ID/HASH/PHONE），跳过搬运。")
            return

        client = TelegramClient(
            str(settings.session_path),
            settings.api_id,
            settings.api_hash,
        )
        self.client = client

        log.info("user-bot 启动中…")
        await client.start(phone=settings.phone)
        log.info("user-bot 已登录")

        client.add_event_handler(self._on_message, events.NewMessage())

        await asyncio.gather(
            self._refresh_loop(),
            client.run_until_disconnected(),
        )


manager = ForwardManager()


async def start_userbot() -> None:
    await manager.run()
