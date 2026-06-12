"""Offline self-test: drives the demo match through its lifecycle and asserts
that kickoff / goal / half-time / full-time events are detected in order.

Run with:  python -m worldcup_bot selftest
"""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone

from .models import (FINISHED, IN_PLAY, PAUSED, TIMED, Match)
from .notifier import diff_events


def _m(status, h, a, mid="x"):
    return Match(id=mid, utc_date=datetime.now(timezone.utc), status=status,
                 home="A", away="B", home_score=h, away_score=a)


def _check(name, got, want):
    ok = got == want
    print(f"  {'✅' if ok else '❌'} {name}: got={got} want={want}")
    return ok


def run_selftest() -> bool:
    ok = True
    print("1) 事件检测 diff_events()")

    # baseline (no prev) -> nothing
    ok &= _check("baseline silent", diff_events(None, _m(TIMED, None, None)), [])

    prev = {"status": TIMED, "home_score": None, "away_score": None, "reminded": 0}
    ok &= _check("kickoff", diff_events(prev, _m(IN_PLAY, 0, 0)), ["kickoff"])

    prev = {"status": IN_PLAY, "home_score": 0, "away_score": 0}
    ok &= _check("home goal", diff_events(prev, _m(IN_PLAY, 1, 0)), ["goal_home"])

    prev = {"status": IN_PLAY, "home_score": 1, "away_score": 0}
    ok &= _check("away goal", diff_events(prev, _m(IN_PLAY, 1, 1)), ["goal_away"])

    prev = {"status": IN_PLAY, "home_score": 1, "away_score": 1}
    ok &= _check("halftime", diff_events(prev, _m(PAUSED, 1, 1)), ["halftime"])

    prev = {"status": IN_PLAY, "home_score": 2, "away_score": 1}
    ok &= _check("fulltime", diff_events(prev, _m(FINISHED, 2, 1)), ["fulltime"])

    prev = {"status": IN_PLAY, "home_score": 1, "away_score": 1}
    ok &= _check("no change", diff_events(prev, _m(IN_PLAY, 1, 1)), [])

    # full pipeline through storage + a fake telegram client
    print("2) 引擎管线 NotificationEngine.process()（含 storage）")
    from .config import Config
    from .storage import Storage
    from .notifier import NotificationEngine

    class FakeTG:
        def __init__(self):
            self.sent = []
        def send_message(self, chat_id, text, **kw):
            self.sent.append((chat_id, text))

    with tempfile.NamedTemporaryFile(suffix=".db") as tf:
        cfg = Config()
        cfg.timezone = "UTC"
        storage = Storage(tf.name)
        storage.add_subscriber("100")
        tg = FakeTG()
        eng = NotificationEngine(storage, tg, cfg)

        eng.process([_m(IN_PLAY, 0, 0, "g1")])          # baseline, silent
        ok &= _check("engine baseline silent", len(tg.sent), 0)
        eng.process([_m(IN_PLAY, 1, 0, "g1")])          # a goal
        ok &= _check("engine goal sent", len(tg.sent), 1)
        eng.process([_m(FINISHED, 1, 0, "g1")])         # full-time
        ok &= _check("engine fulltime sent", len(tg.sent), 2)
        storage.close()

    # demo provider sanity
    print("3) Demo 数据源")
    from .providers.demo import DemoProvider
    dp = DemoProvider(Config())
    ms = dp.get_matches()
    ok &= _check("demo returns matches", len(ms) >= 5, True)
    st = dp.get_standings()
    ok &= _check("demo standings", bool(st), True)

    print("\n" + ("🎉 全部通过 / ALL PASSED" if ok else "💥 有失败项 / FAILURES"))
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if run_selftest() else 1)
