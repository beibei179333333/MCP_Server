"""Normalized data model for matches, shared across providers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# Status values we normalize every provider down to.
SCHEDULED = "SCHEDULED"   # date may still be TBD
TIMED = "TIMED"           # date/time confirmed, not started
IN_PLAY = "IN_PLAY"       # ball rolling
PAUSED = "PAUSED"         # half-time break
FINISHED = "FINISHED"
SUSPENDED = "SUSPENDED"
POSTPONED = "POSTPONED"
CANCELLED = "CANCELLED"

LIVE_STATES = {IN_PLAY, PAUSED}
_FD_STATUS_MAP = {
    "SCHEDULED": SCHEDULED,
    "TIMED": TIMED,
    "IN_PLAY": IN_PLAY,
    "PAUSED": PAUSED,
    "FINISHED": FINISHED,
    "SUSPENDED": SUSPENDED,
    "POSTPONED": POSTPONED,
    "CANCELLED": CANCELLED,
    "CANCELED": CANCELLED,
    "AWARDED": FINISHED,
}


@dataclass
class Match:
    id: str
    utc_date: Optional[datetime]
    status: str
    home: str
    away: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    home_score_ht: Optional[int] = None
    away_score_ht: Optional[int] = None
    winner: Optional[str] = None          # HOME_TEAM | AWAY_TEAM | DRAW | None
    stage: str = ""
    group: str = ""
    matchday: Optional[int] = None
    home_tla: str = ""
    away_tla: str = ""
    minute: Optional[int] = None          # live minute when known
    venue: str = ""                       # stadium / city when known
    extra: dict = field(default_factory=dict)

    # ---- convenience ----------------------------------------------------
    @property
    def is_live(self) -> bool:
        return self.status in LIVE_STATES

    @property
    def is_finished(self) -> bool:
        return self.status == FINISHED

    @property
    def has_score(self) -> bool:
        return self.home_score is not None and self.away_score is not None

    def score_str(self) -> str:
        if self.has_score:
            return f"{self.home_score}-{self.away_score}"
        return "vs"

    def kickoff_in_seconds(self, now: Optional[datetime] = None) -> Optional[float]:
        if self.utc_date is None:
            return None
        now = now or datetime.now(timezone.utc)
        return (self.utc_date - now).total_seconds()

    def signature(self) -> dict:
        """The fields whose change should trigger a notification."""
        return {
            "status": self.status,
            "home_score": self.home_score,
            "away_score": self.away_score,
        }


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # football-data uses e.g. "2026-06-11T19:00:00Z"
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def from_football_data(item: dict) -> Match:
    """Build a Match from a football-data.org v4 ``matches`` entry."""
    score = item.get("score") or {}
    full = score.get("fullTime") or {}
    half = score.get("halfTime") or {}
    home_team = item.get("homeTeam") or {}
    away_team = item.get("awayTeam") or {}
    return Match(
        id=str(item.get("id")),
        utc_date=parse_iso(item.get("utcDate")),
        status=_FD_STATUS_MAP.get(item.get("status", ""), item.get("status", SCHEDULED)),
        home=home_team.get("name") or home_team.get("shortName") or "TBD",
        away=away_team.get("name") or away_team.get("shortName") or "TBD",
        home_score=full.get("home"),
        away_score=full.get("away"),
        home_score_ht=half.get("home"),
        away_score_ht=half.get("away"),
        winner=score.get("winner"),
        stage=item.get("stage", "") or "",
        group=item.get("group") or "",
        matchday=item.get("matchday"),
        home_tla=home_team.get("tla") or "",
        away_tla=away_team.get("tla") or "",
        venue=item.get("venue") or "",
    )
