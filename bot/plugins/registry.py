"""插件注册表 + 配置 -> 实例 工厂。"""
from __future__ import annotations

from typing import Dict, Type

from .base import BasePlugin, PluginChain

REGISTRY: Dict[str, Type[BasePlugin]] = {}


def register(name: str):
    def deco(cls: Type[BasePlugin]):
        cls.name = name
        REGISTRY[name] = cls
        return cls
    return deco


def build_chain(plugins_cfg: dict | None) -> PluginChain:
    plugins_cfg = plugins_cfg or {}
    ordered_keys = [
        "filter", "media", "length", "sender",
        "replace", "format", "caption", "watermark",
    ]
    chain: list[BasePlugin] = []
    for key in ordered_keys:
        if key in plugins_cfg and key in REGISTRY:
            chain.append(REGISTRY[key](plugins_cfg[key]))
    return PluginChain(chain)


# 触发注册（importing 模块会让装饰器执行）
from . import filters as _filters     # noqa: E402,F401
from . import transforms as _trans     # noqa: E402,F401
from . import watermark as _wm         # noqa: E402,F401
