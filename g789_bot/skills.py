"""Load and parse the G789 scenario skill library (S-001 … S-500).

Each scenario lives in ``g789_bot/skills/g789-scenarios-pack-NN/S-XXX-名称/SKILL.md``
and is fully self-contained: the markdown body *is* the system prompt for that
scenario. This module discovers every ``SKILL.md`` once at import time and exposes
a small catalog the Telegram bot can browse, search and serve.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parent / "skills"

# Directory name looks like "S-001-日常购物决策" (the name may itself contain
# hyphens or spaces, e.g. "S-035-OKR 目标拆解").
_DIR_RE = re.compile(r"^(S-\d+)-(.+)$")
_CATEGORY_RE = re.compile(r"所属类目[:：]\**\s*([^\s*]+)")
_DESC_RE = re.compile(r"^description:\s*(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Skill:
    """One self-contained scenario workflow."""

    id: str          # e.g. "S-001"
    num: int         # e.g. 1 (for ordering)
    name: str        # e.g. "日常购物决策"
    category: str    # e.g. "生活"
    description: str  # frontmatter description (English, for matching)
    body: str        # full SKILL.md text — used as the system prompt
    path: Path = field(repr=False)

    @property
    def title(self) -> str:
        return f"{self.id} · {self.name}"


def _parse(path: Path) -> Skill | None:
    m = _DIR_RE.match(path.parent.name)
    if not m:
        return None
    skill_id, name = m.group(1), m.group(2).strip()
    try:
        body = path.read_text(encoding="utf-8")
    except OSError:
        return None

    cat = _CATEGORY_RE.search(body)
    desc = _DESC_RE.search(body)
    return Skill(
        id=skill_id,
        num=int(skill_id.split("-")[1]),
        name=name,
        category=(cat.group(1).strip() if cat else "其他"),
        description=(desc.group(1).strip() if desc else ""),
        body=body,
        path=path,
    )


@lru_cache(maxsize=1)
def load_all() -> list[Skill]:
    """Parse every SKILL.md under :data:`SKILLS_ROOT`, sorted by scenario id."""
    skills: list[Skill] = []
    for md in SKILLS_ROOT.rglob("SKILL.md"):
        skill = _parse(md)
        if skill is not None:
            skills.append(skill)
    skills.sort(key=lambda s: s.num)
    return skills


class Catalog:
    """Indexed, optionally category-filtered view over the skill library."""

    def __init__(self, blocked_categories: set[str] | None = None):
        blocked = blocked_categories or set()
        self._skills = [s for s in load_all() if s.category not in blocked]
        self._by_id = {s.id: s for s in self._skills}
        self._by_cat: dict[str, list[Skill]] = {}
        for s in self._skills:
            self._by_cat.setdefault(s.category, []).append(s)

    def __len__(self) -> int:
        return len(self._skills)

    @property
    def skills(self) -> list[Skill]:
        return self._skills

    def get(self, skill_id: str) -> Skill | None:
        return self._by_id.get(self._normalize_id(skill_id))

    def categories(self) -> list[tuple[str, int]]:
        """(category, count) pairs, most-populated first."""
        return sorted(
            ((c, len(v)) for c, v in self._by_cat.items()),
            key=lambda kv: (-kv[1], kv[0]),
        )

    def in_category(self, category: str) -> list[Skill]:
        return self._by_cat.get(category, [])

    def search(self, query: str, limit: int = 25) -> list[Skill]:
        """Match by id, name, category or description (case-insensitive)."""
        q = query.strip().lower()
        if not q:
            return []

        # Direct id hit (e.g. "S-042" or "42") wins outright.
        direct = self.get(q)
        if direct is not None:
            return [direct]

        scored: list[tuple[int, Skill]] = []
        for s in self._skills:
            haystack = f"{s.id} {s.name} {s.category} {s.description}".lower()
            if q in haystack:
                # Prefer name matches over description-only matches.
                score = 0 if q in s.name.lower() else 1
                scored.append((score, s))
        scored.sort(key=lambda t: (t[0], t[1].num))
        return [s for _, s in scored[:limit]]

    @staticmethod
    def _normalize_id(raw: str) -> str:
        raw = raw.strip().upper()
        m = re.fullmatch(r"S-?(\d+)", raw)
        if m:
            return f"S-{int(m.group(1)):03d}"
        if raw.isdigit():
            return f"S-{int(raw):03d}"
        return raw
