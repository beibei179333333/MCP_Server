"""Detect match events between polls and push them to subscribers."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Optional

from . import formatting as F
from .models import (FINISHED, IN_PLAY, PAUSED, SCHEDULED, TIMED, Match)
from .storage import Storage
from .telegram import TelegramClient, TelegramError

log = logging.getLogger("worldcup_bot.notifier")

# event types and the subscriber setting that gates each one
EVENT_SETTING = {
    "reminder": "notify_reminders",
    "kickoff": "notify_kickoff",
    "goal_home": "notify_goals",
    "goal_away": "notify_goals",
    "halftime": "notify_halftime",
    "fulltime": "notify_fulltime",
}


def diff_events(prev: Optional[dict], m: Match) -> list[str]:
    """Pure transition detector. ``prev`` is a stored state row (or None).

    Returns a list of event type strings (excluding reminders, handled
    separately). On first sight of a match (prev is None) nothing fires —
    that poll only establishes the baseline.
    """
    if prev is None:
        return []
    events: list[str] = []
    prev_status = prev.get("status")
    prev_h = prev.get("home_score")
    prev_a = prev.get("away_score")

    # kickoff
    if prev_status in (SCHEDULED, TIMED) and m.status == IN_PLAY:
        events.append("kickoff")

    # goals (only when we have a real previous scoreline to compare)
    if m.home_score is not None and prev_h is not None and m.home_score > prev_h:
        events.append("goal_home")
    if m.away_score is not None and prev_a is not None and m.away_score > prev_a:
        events.append("goal_away")

    # half-time
    if m.status == PAUSED and prev_status != PAUSED:
        events.append("halftime")

    # full-time
    if m.status == FINISHED and prev_status != FINISHED:
        events.append("fulltime")

    return events


def render_event(event: str, m: Match, tzname: str, reminder_minutes: int, lang: str) -> Optional[str]:
    if event == "reminder":
        return F.event_reminder(m, tzname, reminder_minutes, lang)
    if event == "kickoff":
        return F.event_kickoff(m, lang)
    if event == "goal_home":
        return F.event_goal(m, "home", lang)
    if event == "goal_away":
        return F.event_goal(m, "away", lang)
    if event == "halftime":
        return F.event_halftime(m, lang)
    if event == "fulltime":
        return F.event_fulltime(m, lang)
    return None


class NotificationEngine:
    def __init__(self, storage: Storage, telegram: TelegramClient, cfg):
        self.storage = storage
        self.tg = telegram
        self.cfg = cfg

    def process(self, matches: Iterable[Match], now: Optional[datetime] = None) -> int:
        """Run one detection pass over current matches; returns events sent."""
        now = now or datetime.now(timezone.utc)
        sent = 0
        for m in matches:
            prev = self.storage.get_match_state(m.id)
            events = diff_events(prev, m)

            # pre-kickoff reminder (independent of status transitions)
            reminded = bool(prev and prev.get("reminded"))
            if not reminded and m.status in (SCHEDULED, TIMED):
                secs = m.kickoff_in_seconds(now)
                if secs is not None and 0 < secs <= self.cfg.reminder_minutes * 60:
                    events = ["reminder"] + events
                    self.storage.upsert_match_state(
                        m.id, m.status, m.home_score, m.away_score, reminded=1
                    )

            for event in events:
                sent += self._broadcast(event, m)

            # persist the new baseline (keeps reminded flag)
            self.storage.upsert_match_state(m.id, m.status, m.home_score, m.away_score)
        return sent

    def _broadcast(self, event: str, m: Match) -> int:
        setting = EVENT_SETTING.get(event)
        count = 0
        for sub in self.storage.all_subscribers():
            if setting and not sub.get(setting, 1):
                continue
            lang = sub.get("lang", self.cfg.default_lang)
            text = render_event(event, m, self.cfg.timezone, self.cfg.reminder_minutes, lang)
            if not text:
                continue
            try:
                self.tg.send_message(sub["chat_id"], text)
                count += 1
            except TelegramError as exc:
                msg = str(exc)
                # drop chats that blocked the bot or no longer exist
                if "bot was blocked" in msg or "chat not found" in msg or "user is deactivated" in msg:
                    log.info("removing dead subscriber %s (%s)", sub["chat_id"], msg)
                    self.storage.remove_subscriber(sub["chat_id"])
                else:
                    log.warning("send to %s failed: %s", sub["chat_id"], msg)
        if count:
            log.info("event %s for %s -> %d chats", event, m.id, count)
        return count
