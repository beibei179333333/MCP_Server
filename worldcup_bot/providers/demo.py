"""Demo provider — realistic, network-free data so the bot runs without a key.

It also drives ONE accelerated "live" match through its whole lifecycle
(kickoff → goals → half-time → full-time) over ``demo_seconds_per_match``
seconds, anchored on the first call, so you can actually watch the live
notifications fire end-to-end. Set a short POLL_INTERVAL_SECONDS to see every
event (the bot does this automatically in demo mode).
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..config import Config
from ..models import (FINISHED, IN_PLAY, PAUSED, TIMED, Match)

_ANCHOR_KEY = "demo_anchor"


class DemoProvider:
    name = "demo"

    def __init__(self, cfg: Config, storage=None):
        self.cfg = cfg
        self.storage = storage
        self._mem_anchor: Optional[float] = None

    # -- anchor persistence so the timeline is stable across polls/restarts
    def _anchor(self) -> float:
        if self.storage is not None:
            val = self.storage.get_meta(_ANCHOR_KEY)
            if val is None:
                now = str(time.time())
                self.storage.set_meta(_ANCHOR_KEY, now)
                return float(now)
            return float(val)
        if self._mem_anchor is None:
            self._mem_anchor = time.time()
        return self._mem_anchor

    def _live_match(self) -> Match:
        total = max(60, self.cfg.demo_seconds_per_match)
        elapsed = time.time() - self._anchor()
        f = elapsed / total  # 0..1+ progress fraction

        # scripted scoreline + status by progress fraction
        if f < 0.08:
            status, hs, as_ = TIMED, None, None
        elif f < 0.15:
            status, hs, as_ = IN_PLAY, 0, 0
        elif f < 0.40:
            status, hs, as_ = IN_PLAY, 1, 0
        elif f < 0.50:
            status, hs, as_ = IN_PLAY, 1, 1
        elif f < 0.60:
            status, hs, as_ = PAUSED, 1, 1
        elif f < 0.75:
            status, hs, as_ = IN_PLAY, 1, 1
        elif f < 1.0:
            status, hs, as_ = IN_PLAY, 2, 1
        else:
            status, hs, as_ = FINISHED, 2, 1

        minute = None
        if status in (IN_PLAY, PAUSED):
            minute = int(min(90, max(1, f * 90)))
        winner = None
        ht_h = ht_a = None
        if f >= 0.5:
            ht_h, ht_a = 1, 1
        if status == FINISHED:
            winner = "HOME_TEAM"

        kickoff = datetime.fromtimestamp(self._anchor(), tz=timezone.utc) + timedelta(
            seconds=total * 0.08
        )
        return Match(
            id="demo-live-1",
            utc_date=kickoff,
            status=status,
            home="Argentina",
            away="Brazil",
            home_score=hs,
            away_score=as_,
            home_score_ht=ht_h,
            away_score_ht=ht_a,
            winner=winner,
            stage="GROUP_STAGE",
            group="GROUP_A",
            matchday=2,
            home_tla="ARG",
            away_tla="BRA",
            minute=minute,
        )

    def get_matches(self) -> list[Match]:
        now = datetime.now(timezone.utc)
        matches = [
            Match(
                id="demo-fin-1", utc_date=now - timedelta(hours=27), status=FINISHED,
                home="Argentina", away="Mexico", home_score=2, away_score=0,
                home_score_ht=1, away_score_ht=0, winner="HOME_TEAM",
                stage="GROUP_STAGE", group="GROUP_A", matchday=1,
                home_tla="ARG", away_tla="MEX",
            ),
            Match(
                id="demo-fin-2", utc_date=now - timedelta(hours=24), status=FINISHED,
                home="Brazil", away="Canada", home_score=3, away_score=1,
                home_score_ht=2, away_score_ht=0, winner="HOME_TEAM",
                stage="GROUP_STAGE", group="GROUP_A", matchday=1,
                home_tla="BRA", away_tla="CAN",
            ),
            self._live_match(),
            Match(
                id="demo-up-1", utc_date=now + timedelta(hours=3), status=TIMED,
                home="Mexico", away="Canada", stage="GROUP_STAGE",
                group="GROUP_A", matchday=2, home_tla="MEX", away_tla="CAN",
            ),
            Match(
                id="demo-up-2", utc_date=now + timedelta(days=1, hours=2), status=TIMED,
                home="France", away="Spain", stage="GROUP_STAGE",
                group="GROUP_B", matchday=1, home_tla="FRA", away_tla="ESP",
            ),
            Match(
                id="demo-up-3", utc_date=now + timedelta(days=1, hours=5), status=TIMED,
                home="England", away="Germany", stage="GROUP_STAGE",
                group="GROUP_B", matchday=1, home_tla="ENG", away_tla="GER",
            ),
            Match(
                id="demo-up-4", utc_date=now + timedelta(days=2, hours=2), status=TIMED,
                home="Portugal", away="Netherlands", stage="GROUP_STAGE",
                group="GROUP_C", matchday=1, home_tla="POR", away_tla="NED",
            ),
        ]
        return matches

    def get_standings(self) -> Optional[list[dict]]:
        groups: dict[str, dict[str, dict]] = {}
        for m in self.get_matches():
            if m.stage != "GROUP_STAGE" or not m.is_finished or not m.has_score:
                continue
            g = (m.group or "").replace("_", " ").title()
            tbl = groups.setdefault(g, {})
            for team in (m.home, m.away):
                tbl.setdefault(team, dict(team=team, played=0, won=0, draw=0,
                                          lost=0, gf=0, ga=0, points=0))
            h, a = tbl[m.home], tbl[m.away]
            h["played"] += 1; a["played"] += 1
            h["gf"] += m.home_score; h["ga"] += m.away_score
            a["gf"] += m.away_score; a["ga"] += m.home_score
            if m.home_score > m.away_score:
                h["won"] += 1; h["points"] += 3; a["lost"] += 1
            elif m.home_score < m.away_score:
                a["won"] += 1; a["points"] += 3; h["lost"] += 1
            else:
                h["draw"] += 1; a["draw"] += 1; h["points"] += 1; a["points"] += 1

        out = []
        for g, tbl in sorted(groups.items()):
            rows = sorted(tbl.values(),
                          key=lambda r: (r["points"], r["gf"] - r["ga"], r["gf"]),
                          reverse=True)
            for i, r in enumerate(rows, 1):
                r["position"] = i
                r["gd"] = r["gf"] - r["ga"]
            out.append({"group": g, "table": rows})
        return out or None
