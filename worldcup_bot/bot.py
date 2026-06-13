"""Command handling + the main run loop (commands thread + polling thread)."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from . import formatting as F
from .config import Config
from .i18n import STAGE_ORDER, stage_name, t
from .models import LIVE_STATES, Match
from .notifier import NotificationEngine
from .providers import build_provider
from .storage import SETTING_FIELDS, Storage
from .telegram import TelegramClient, TelegramError

log = logging.getLogger("worldcup_bot.bot")

_SETTING_LABELS = {
    "notify_reminders": "reminder",
    "notify_kickoff": "kickoff",
    "notify_goals": "goals",
    "notify_halftime": "halftime",
    "notify_fulltime": "fulltime",
}


class WorldCupBot:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.storage = Storage(cfg.db_path, default_lang=cfg.default_lang)
        self.provider = build_provider(cfg, storage=self.storage)
        # separate clients for the two threads to avoid Session contention
        self.tg = TelegramClient(cfg.telegram_token, timeout=cfg.request_timeout)
        self.tg_push = TelegramClient(cfg.telegram_token, timeout=cfg.request_timeout)
        self.engine = NotificationEngine(self.storage, self.tg_push, cfg)
        self.stop = threading.Event()
        self._offset = None

    # ---- helpers --------------------------------------------------------
    def _lang(self, chat_id: str) -> str:
        sub = self.storage.get_subscriber(chat_id)
        return sub["lang"] if sub else self.cfg.default_lang

    def _matches(self) -> list[Match]:
        try:
            return self.provider.get_matches()
        except Exception as exc:  # provider should be defensive, but be safe
            log.warning("get_matches failed: %s", exc)
            return []

    def _reply(self, chat_id: str, text: str, reply_markup=None) -> None:
        try:
            self.tg.send_message(chat_id, text, reply_markup=reply_markup)
        except TelegramError as exc:
            log.warning("reply to %s failed: %s", chat_id, exc)

    def _reply_chunks(self, chat_id: str, chunks: list[str]) -> None:
        for part in chunks:
            self._reply(chat_id, part)

    # ---- keyboards ------------------------------------------------------
    def _settings_keyboard(self, chat_id: str) -> dict:
        sub = self.storage.get_subscriber(chat_id) or {}
        lang = sub.get("lang", self.cfg.default_lang)
        rows = []
        for field in SETTING_FIELDS:
            on = bool(sub.get(field, 1))
            mark = "✅" if on else "⬜️"
            label = t(_SETTING_LABELS[field], lang)
            rows.append([{ "text": f"{mark} {label}", "callback_data": f"set:{field}" }])
        return {"inline_keyboard": rows}

    def _lang_keyboard(self) -> dict:
        return {"inline_keyboard": [[
            {"text": "🇨🇳 中文", "callback_data": "lang:zh"},
            {"text": "🇬🇧 English", "callback_data": "lang:en"},
        ]]}

    def _schedule_keyboard(self, lang: str) -> dict:
        rows, row = [], []
        for code, emoji in STAGE_ORDER:
            row.append({"text": f"{emoji} {stage_name(code, lang)}",
                        "callback_data": f"sched:{code}"})
            if len(row) == 2:
                rows.append(row); row = []
        if row:
            rows.append(row)
        return {"inline_keyboard": rows}

    # ---- command handlers ----------------------------------------------
    def cmd_start(self, chat_id: str, _args: str) -> None:
        self.storage.add_subscriber(chat_id, self.cfg.default_lang)
        lang = self._lang(chat_id)
        self._reply(chat_id, t("welcome", lang))
        if self.cfg.is_demo:
            self._reply(chat_id, t("demo_note", lang))

    def cmd_help(self, chat_id: str, _args: str) -> None:
        self._reply(chat_id, t("help", self._lang(chat_id)))

    def cmd_subscribe(self, chat_id: str, _args: str) -> None:
        lang = self._lang(chat_id)
        added = self.storage.add_subscriber(chat_id, self.cfg.default_lang)
        self._reply(chat_id, t("subscribed" if added else "already_sub", lang))

    def cmd_unsubscribe(self, chat_id: str, _args: str) -> None:
        lang = self._lang(chat_id)
        removed = self.storage.remove_subscriber(chat_id)
        self._reply(chat_id, t("unsubscribed" if removed else "not_sub", lang))

    def cmd_today(self, chat_id: str, _args: str) -> None:
        lang = self._lang(chat_id)
        tz = F._tz(self.cfg.timezone)
        today = datetime.now(tz).date()
        todays = [m for m in self._matches()
                  if m.utc_date and m.utc_date.astimezone(tz).date() == today]
        todays.sort(key=lambda m: m.utc_date)
        self._reply(chat_id, F.match_list(t("today_title", lang), todays,
                                          self.cfg.timezone, lang, t("no_today", lang)))

    def cmd_live(self, chat_id: str, _args: str) -> None:
        lang = self._lang(chat_id)
        live = [m for m in self._matches() if m.status in LIVE_STATES]
        live.sort(key=lambda m: (m.utc_date or datetime.max.replace(tzinfo=timezone.utc)))
        self._reply(chat_id, F.match_list(t("live_title", lang), live,
                                          self.cfg.timezone, lang, t("no_live", lang)))

    def cmd_next(self, chat_id: str, _args: str) -> None:
        lang = self._lang(chat_id)
        now = datetime.now(timezone.utc)
        upcoming = [m for m in self._matches()
                    if m.utc_date and m.utc_date > now and not m.is_finished and not m.is_live]
        upcoming.sort(key=lambda m: m.utc_date)
        self._reply(chat_id, F.match_list(t("next_title", lang), upcoming[:5],
                                          self.cfg.timezone, lang, t("no_next", lang)))

    def cmd_matches(self, chat_id: str, _args: str) -> None:
        lang = self._lang(chat_id)
        now = datetime.now(timezone.utc)
        ms = [m for m in self._matches() if m.utc_date]
        ms.sort(key=lambda m: m.utc_date)
        # window: live + finished in last 24h + next upcoming, capped for length
        window = [m for m in ms if m.is_live
                  or (m.is_finished and (now - m.utc_date).total_seconds() < 86400)
                  or m.utc_date >= now]
        self._reply(chat_id, F.match_list(t("matches_title", lang), window[:25],
                                          self.cfg.timezone, lang, t("no_matches", lang)))

    def cmd_schedule(self, chat_id: str, args: str) -> None:
        lang = self._lang(chat_id)
        arg = (args or "").strip().upper()
        # /schedule final -> jump straight to that round
        if arg:
            alias = {"R32": "LAST_32", "R16": "LAST_16", "QF": "QUARTER_FINALS",
                     "SF": "SEMI_FINALS", "GROUP": "GROUP_STAGE",
                     "GROUPS": "GROUP_STAGE", "FINAL": "FINAL"}.get(arg, arg)
            self._reply_chunks(chat_id, F.stage_schedule(
                self._matches(), alias, self.cfg.timezone, lang))
            return
        self._reply(chat_id, t("schedule_overview", lang),
                    reply_markup=self._schedule_keyboard(lang))

    def cmd_standings(self, chat_id: str, _args: str) -> None:
        lang = self._lang(chat_id)
        try:
            groups = self.provider.get_standings()
        except Exception as exc:
            log.warning("get_standings failed: %s", exc)
            groups = None
        if not groups:
            self._reply(chat_id, t("standings_na", lang))
            return
        self._reply(chat_id, F.standings_block(groups, lang))

    def cmd_settings(self, chat_id: str, _args: str) -> None:
        lang = self._lang(chat_id)
        if not self.storage.is_subscribed(chat_id):
            self._reply(chat_id, t("not_sub", lang))
            return
        self._reply(chat_id, t("settings_title", lang),
                    reply_markup=self._settings_keyboard(chat_id))

    def cmd_lang(self, chat_id: str, _args: str) -> None:
        lang = self._lang(chat_id)
        self._reply(chat_id, t("lang_choose", lang), reply_markup=self._lang_keyboard())

    def cmd_whoami(self, chat_id: str, _args: str) -> None:
        self._reply(chat_id, t("whoami", self._lang(chat_id), cid=chat_id))

    def cmd_broadcast(self, chat_id: str, args: str) -> None:
        if not self.cfg.admin_chat_id or str(chat_id) != str(self.cfg.admin_chat_id):
            self._reply(chat_id, t("unknown_cmd", self._lang(chat_id)))
            return
        text = args.strip()
        if not text:
            self._reply(chat_id, "用法 / usage: /broadcast <message>")
            return
        sent = 0
        for sub in self.storage.all_subscribers():
            try:
                self.tg.send_message(sub["chat_id"], f"📢 {text}")
                sent += 1
            except TelegramError:
                pass
        self._reply(chat_id, f"已发送给 {sent} 个会话 / sent to {sent} chats")

    COMMANDS = {
        "start": cmd_start, "help": cmd_help,
        "subscribe": cmd_subscribe, "unsubscribe": cmd_unsubscribe, "stop": cmd_unsubscribe,
        "today": cmd_today, "live": cmd_live, "next": cmd_next,
        "matches": cmd_matches, "schedule": cmd_schedule, "fixtures": cmd_schedule,
        "standings": cmd_standings, "groups": cmd_standings,
        "settings": cmd_settings, "lang": cmd_lang, "language": cmd_lang,
        "whoami": cmd_whoami, "broadcast": cmd_broadcast,
    }

    # ---- dispatch -------------------------------------------------------
    def _handle_message(self, msg: dict) -> None:
        chat = msg.get("chat") or {}
        chat_id = str(chat.get("id"))
        text = (msg.get("text") or "").strip()
        if not chat_id or not text.startswith("/"):
            return
        cmd, _, args = text[1:].partition(" ")
        cmd = cmd.split("@", 1)[0].lower()
        handler = self.COMMANDS.get(cmd)
        if handler is None:
            self._reply(chat_id, t("unknown_cmd", self._lang(chat_id)))
            return
        try:
            handler(self, chat_id, args)
        except Exception:
            log.exception("handler for /%s failed", cmd)

    def _handle_callback(self, cq: dict) -> None:
        data = cq.get("data") or ""
        msg = cq.get("message") or {}
        chat = msg.get("chat") or {}
        chat_id = str(chat.get("id"))
        message_id = msg.get("message_id")
        cq_id = cq.get("id")
        if data.startswith("sched:"):
            code = data[6:]
            lang = self._lang(chat_id)
            self.tg.answer_callback(cq_id, stage_name(code, lang))
            self._reply_chunks(chat_id, F.stage_schedule(
                self._matches(), code, self.cfg.timezone, lang))
            return
        if data.startswith("set:"):
            field = data[4:]
            new_val = self.storage.toggle_setting(chat_id, field)
            lang = self._lang(chat_id)
            label = t(_SETTING_LABELS.get(field, field), lang)
            state = t("on" if new_val else "off", lang)
            self.tg.answer_callback(cq_id, f"{label}: {state}")
            if message_id is not None:
                self.tg.edit_reply_markup(chat_id, message_id, self._settings_keyboard(chat_id))
        elif data.startswith("lang:"):
            lang = data[5:]
            if lang not in {"zh", "en"}:
                lang = "zh"
            if not self.storage.is_subscribed(chat_id):
                self.storage.add_subscriber(chat_id, lang)
            self.storage.set_lang(chat_id, lang)
            self.tg.answer_callback(cq_id, t("lang_set", lang))
            self._reply(chat_id, t("lang_set", lang))
        else:
            self.tg.answer_callback(cq_id)

    def _dispatch(self, update: dict) -> None:
        self._offset = update["update_id"] + 1
        if "message" in update:
            self._handle_message(update["message"])
        elif "callback_query" in update:
            self._handle_callback(update["callback_query"])

    # ---- loops ----------------------------------------------------------
    def command_loop(self) -> None:
        log.info("command loop started")
        while not self.stop.is_set():
            try:
                updates = self.tg.get_updates(offset=self._offset, timeout=25)
                for upd in updates:
                    self._dispatch(upd)
            except TelegramError as exc:
                log.warning("getUpdates failed: %s; retrying in 5s", exc)
                self.stop.wait(5)
            except Exception:
                log.exception("command loop error; retrying in 5s")
                self.stop.wait(5)
        log.info("command loop stopped")

    def poll_loop(self) -> None:
        log.info("poll loop started (interval=%ss, provider=%s)",
                 self.cfg.poll_interval, self.provider.name)
        # seed baseline immediately so we don't blast existing match states
        try:
            self.engine.process(self._matches())
        except Exception:
            log.exception("baseline poll failed")
        while not self.stop.wait(self.cfg.poll_interval):
            try:
                self.engine.process(self._matches())
            except Exception:
                log.exception("poll iteration failed")
        log.info("poll loop stopped")

    def run(self) -> None:
        me = self.tg.get_me()
        log.info("Bot @%s is live. Provider=%s, tz=%s",
                 me.get("username"), self.provider.name, self.cfg.timezone)
        for w in self.cfg.warnings:
            log.warning(w)
        poll_thread = threading.Thread(target=self.poll_loop, name="poll", daemon=True)
        poll_thread.start()
        try:
            self.command_loop()
        finally:
            self.stop.set()
            poll_thread.join(timeout=5)
            self.storage.close()
