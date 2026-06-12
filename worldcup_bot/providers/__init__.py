"""Match data providers."""
from __future__ import annotations

from ..config import Config
from .base import Provider
from .demo import DemoProvider
from .football_data import FootballDataProvider


def build_provider(cfg: Config, storage=None) -> Provider:
    if cfg.provider == "demo":
        return DemoProvider(cfg, storage=storage)
    return FootballDataProvider(cfg)
