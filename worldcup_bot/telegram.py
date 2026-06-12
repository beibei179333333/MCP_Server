"""Minimal Telegram Bot API client built on requests (no extra deps).

Only the handful of methods the bot needs: getMe, getUpdates (long polling),
sendMessage and answerCallbackQuery / editMessageReplyMarkup.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import requests

log = logging.getLogger("worldcup_bot.telegram")


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str, timeout: int = 20):
        if not token:
            raise TelegramError("缺少 TELEGRAM_BOT_TOKEN")
        self.token = token
        self.base = f"https://api.telegram.org/bot{token}"
        self.timeout = timeout
        self._session = requests.Session()

    def _call(self, method: str, params: Optional[dict] = None, timeout: Optional[int] = None) -> Any:
        url = f"{self.base}/{method}"
        try:
            resp = self._session.post(url, json=params or {}, timeout=timeout or self.timeout)
        except requests.RequestException as exc:
            raise TelegramError(f"{method} 请求失败: {exc}") from exc
        try:
            data = resp.json()
        except ValueError as exc:
            raise TelegramError(f"{method} 返回非 JSON: {resp.text[:200]}") from exc
        if not data.get("ok"):
            raise TelegramError(f"{method} 失败: {data.get('description')}")
        return data.get("result")

    def get_me(self) -> dict:
        return self._call("getMe")

    def get_updates(self, offset: Optional[int] = None, timeout: int = 25) -> list[dict]:
        params = {
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            params["offset"] = offset
        # network read timeout must exceed the long-poll timeout
        return self._call("getUpdates", params, timeout=timeout + 10) or []

    def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: Optional[dict] = None,
        disable_preview: bool = True,
    ) -> Optional[dict]:
        params = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview,
        }
        if reply_markup is not None:
            params["reply_markup"] = reply_markup
        return self._call("sendMessage", params)

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        try:
            self._call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})
        except TelegramError as exc:
            log.warning("answerCallbackQuery failed: %s", exc)

    def edit_reply_markup(self, chat_id: str, message_id: int, reply_markup: dict) -> None:
        try:
            self._call(
                "editMessageReplyMarkup",
                {"chat_id": chat_id, "message_id": message_id, "reply_markup": reply_markup},
            )
        except TelegramError as exc:
            log.warning("editMessageReplyMarkup failed: %s", exc)
