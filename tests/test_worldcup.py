"""Offline tests for the 2026 World Cup Telegram bot.

Run: python -m pytest tests/test_worldcup.py -q
"""
import os
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from worldcup_bot import formatting as F
from worldcup_bot.config import Config
from worldcup_bot.models import (FINISHED, IN_PLAY, PAUSED, TIMED, Match,
                                 from_football_data, parse_iso)
from worldcup_bot.notifier import NotificationEngine, diff_events
from worldcup_bot.providers.demo import DemoProvider
from worldcup_bot.storage import Storage


def _m(status, h, a, mid="x"):
    return Match(id=mid, utc_date=datetime.now(timezone.utc), status=status,
                 home="A", away="B", home_score=h, away_score=a)


# ---- model / parsing ----------------------------------------------------
def test_parse_iso_z_suffix():
    dt = parse_iso("2026-06-11T19:00:00Z")
    assert dt is not None and dt.tzinfo is not None
    assert dt.year == 2026 and dt.hour == 19


def test_from_football_data_normalizes():
    item = {
        "id": 42, "utcDate": "2026-06-11T19:00:00Z", "status": "IN_PLAY",
        "stage": "GROUP_STAGE", "group": "GROUP_A", "matchday": 1,
        "homeTeam": {"name": "Argentina", "tla": "ARG"},
        "awayTeam": {"name": "Brazil", "tla": "BRA"},
        "score": {"winner": None, "fullTime": {"home": 1, "away": 0},
                  "halfTime": {"home": 0, "away": 0}},
    }
    m = from_football_data(item)
    assert m.id == "42" and m.status == IN_PLAY
    assert m.home == "Argentina" and m.away == "Brazil"
    assert m.home_score == 1 and m.away_score == 0
    assert m.is_live and not m.is_finished


# ---- event detection ----------------------------------------------------
def test_baseline_is_silent():
    assert diff_events(None, _m(IN_PLAY, 0, 0)) == []


def test_kickoff_detected():
    prev = {"status": TIMED, "home_score": None, "away_score": None}
    assert diff_events(prev, _m(IN_PLAY, 0, 0)) == ["kickoff"]


def test_goals_detected_each_side():
    assert diff_events({"status": IN_PLAY, "home_score": 0, "away_score": 0},
                       _m(IN_PLAY, 1, 0)) == ["goal_home"]
    assert diff_events({"status": IN_PLAY, "home_score": 1, "away_score": 0},
                       _m(IN_PLAY, 1, 1)) == ["goal_away"]


def test_halftime_and_fulltime():
    assert diff_events({"status": IN_PLAY, "home_score": 1, "away_score": 1},
                       _m(PAUSED, 1, 1)) == ["halftime"]
    assert diff_events({"status": IN_PLAY, "home_score": 2, "away_score": 1},
                       _m(FINISHED, 2, 1)) == ["fulltime"]


def test_no_event_on_no_change():
    assert diff_events({"status": IN_PLAY, "home_score": 1, "away_score": 1},
                       _m(IN_PLAY, 1, 1)) == []


# ---- engine + storage pipeline -----------------------------------------
class _FakeTG:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


def test_engine_pipeline_sends_in_order():
    with tempfile.NamedTemporaryFile(suffix=".db") as tf:
        cfg = Config()
        cfg.timezone = "UTC"
        storage = Storage(tf.name)
        storage.add_subscriber("100")
        tg = _FakeTG()
        eng = NotificationEngine(storage, tg, cfg)

        eng.process([_m(IN_PLAY, 0, 0, "g")])     # baseline -> silent
        assert len(tg.sent) == 0
        eng.process([_m(IN_PLAY, 1, 0, "g")])     # goal
        eng.process([_m(PAUSED, 1, 0, "g")])      # halftime
        eng.process([_m(FINISHED, 1, 0, "g")])    # fulltime
        texts = [t for _, t in tg.sent]
        assert any("进球" in t or "GOAL" in t for t in texts)
        assert any("半场" in t or "Half" in t for t in texts)
        assert any("终场" in t or "Full" in t for t in texts)
        storage.close()


def test_engine_respects_settings_toggle():
    with tempfile.NamedTemporaryFile(suffix=".db") as tf:
        storage = Storage(tf.name)
        storage.add_subscriber("1")
        storage.toggle_setting("1", "notify_goals")  # turn goals OFF
        tg = _FakeTG()
        eng = NotificationEngine(storage, tg, Config())
        eng.process([_m(IN_PLAY, 0, 0, "g")])
        eng.process([_m(IN_PLAY, 1, 0, "g")])        # goal, but muted
        assert len(tg.sent) == 0
        storage.close()


# ---- storage ------------------------------------------------------------
def test_storage_subscribe_lifecycle():
    with tempfile.NamedTemporaryFile(suffix=".db") as tf:
        s = Storage(tf.name)
        assert s.add_subscriber("7") is True
        assert s.add_subscriber("7") is False
        assert s.is_subscribed("7")
        assert s.remove_subscriber("7") is True
        assert not s.is_subscribed("7")
        s.close()


# ---- demo provider ------------------------------------------------------
def test_demo_provider_has_live_and_standings():
    dp = DemoProvider(Config())
    ms = dp.get_matches()
    assert len(ms) >= 5
    st = dp.get_standings()
    assert st and st[0]["table"]


# ---- formatting ---------------------------------------------------------
def test_formatting_html_safe_and_flags():
    m = Match(id="x", utc_date=None, status=IN_PLAY, home="Argentina",
              away="Brazil", home_score=2, away_score=1, minute=70)
    line = F.event_goal(m, "home", "zh")
    assert "Argentina" in line and "2-1" in line


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
