"""football-data.org v4 provider (free tier supports the World Cup, code WC).

Get a free API key at https://www.football-data.org/ and set
FOOTBALL_DATA_API_KEY. Responses are cached briefly to respect the free-tier
rate limit (10 requests/min).
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import requests

from ..config import Config
from ..models import Match, from_football_data

log = logging.getLogger("worldcup_bot.football_data")

BASE = "https://api.football-data.org/v4"


class FootballDataProvider:
    name = "football-data"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._session = requests.Session()
        self._session.headers.update({"X-Auth-Token": cfg.football_data_key})
        self._cache: dict[str, tuple[float, object]] = {}
        self._cache_ttl = max(15, min(cfg.poll_interval - 5, 50))

    def _get(self, path: str) -> Optional[dict]:
        now = time.time()
        cached = self._cache.get(path)
        if cached and now - cached[0] < self._cache_ttl:
            return cached[1]
        url = f"{BASE}{path}"
        try:
            resp = self._session.get(url, timeout=self.cfg.request_timeout)
        except requests.RequestException as exc:
            log.warning("football-data request failed (%s): %s", path, exc)
            return cached[1] if cached else None
        if resp.status_code == 429:
            log.warning("football-data rate limited (429); using cache if available")
            return cached[1] if cached else None
        if resp.status_code != 200:
            log.warning("football-data %s -> HTTP %s: %s", path, resp.status_code, resp.text[:160])
            return cached[1] if cached else None
        try:
            data = resp.json()
        except ValueError:
            log.warning("football-data %s returned non-JSON", path)
            return cached[1] if cached else None
        self._cache[path] = (now, data)
        return data

    def get_matches(self) -> list[Match]:
        data = self._get(f"/competitions/{self.cfg.competition}/matches")
        if not data:
            return []
        return [from_football_data(m) for m in data.get("matches", [])]

    def get_standings(self) -> Optional[list[dict]]:
        data = self._get(f"/competitions/{self.cfg.competition}/standings")
        if not data:
            return None
        out: list[dict] = []
        for st in data.get("standings", []):
            if st.get("type") != "TOTAL":
                continue
            group = st.get("group") or st.get("stage") or ""
            table = []
            for row in st.get("table", []):
                team = row.get("team") or {}
                table.append({
                    "position": row.get("position"),
                    "team": team.get("name") or team.get("shortName") or "TBD",
                    "played": row.get("playedGames"),
                    "won": row.get("won"),
                    "draw": row.get("draw"),
                    "lost": row.get("lost"),
                    "gf": row.get("goalsFor"),
                    "ga": row.get("goalsAgainst"),
                    "gd": row.get("goalDifference"),
                    "points": row.get("points"),
                })
            if table:
                out.append({"group": (group or "").replace("_", " ").title(), "table": table})
        return out or None
