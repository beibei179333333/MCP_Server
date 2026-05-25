"""Dedup / merge / filter pipeline over normalized members."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Tuple

from .filters import FilterConfig, classify
from .models import Member


@dataclass
class PipelineStats:
    seen: int = 0
    unique: int = 0
    merged: int = 0
    filtered: Dict[str, int] = field(default_factory=dict)
    kept: int = 0

    def add_filter(self, reason: str) -> None:
        self.filtered[reason] = self.filtered.get(reason, 0) + 1

    @property
    def total_filtered(self) -> int:
        return sum(self.filtered.values())


def dedup_merge(members: Iterable[Member]) -> Tuple[List[Member], PipelineStats]:
    """Collapse members sharing a dedup_key, merging their fields."""
    stats = PipelineStats()
    index: Dict[str, Member] = {}
    for m in members:
        stats.seen += 1
        key = m.dedup_key
        if key in index:
            index[key].merge(m)
            stats.merged += 1
        else:
            index[key] = m
    out = list(index.values())
    stats.unique = len(out)
    return out, stats


def apply_filters(
    members: Iterable[Member], cfg: FilterConfig, stats: PipelineStats
) -> Tuple[List[Member], List[Tuple[Member, str]]]:
    kept: List[Member] = []
    removed: List[Tuple[Member, str]] = []
    for m in members:
        reason = classify(m, cfg)
        if reason:
            stats.add_filter(reason)
            removed.append((m, reason))
        else:
            kept.append(m)
    stats.kept = len(kept)
    return kept, removed


def run(
    raw_members: Iterable[Member], cfg: FilterConfig
) -> Tuple[List[Member], List[Tuple[Member, str]], PipelineStats]:
    """Full pipeline: dedup+merge, then filter. Returns (kept, removed, stats)."""
    deduped, stats = dedup_merge(raw_members)
    kept, removed = apply_filters(deduped, cfg, stats)
    # Stable, useful ordering: most active first, then by username.
    kept.sort(key=lambda m: (-m.message_count, m.username.lower(), m.user_id))
    return kept, removed, stats
