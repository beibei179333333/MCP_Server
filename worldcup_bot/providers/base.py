"""Provider interface."""
from __future__ import annotations

from typing import Optional

from ..models import Match


class Provider:
    name = "base"

    def get_matches(self) -> list[Match]:
        """Return the full list of competition matches (any status)."""
        raise NotImplementedError

    def get_standings(self) -> Optional[list[dict]]:
        """Return group standings or None if unsupported/unavailable.

        Each item: {"group": "Group A", "table": [
            {"position": 1, "team": "...", "played": 3, "won": 2,
             "draw": 1, "lost": 0, "gf": 5, "ga": 2, "gd": 3, "points": 7}, ...]}
        """
        return None
