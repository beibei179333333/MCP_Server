"""搬运插件系统（参考 tgcf）。

每条 ForwardRule 的 `plugins` JSON 形如：
{
    "filter":   {"keywords": ["优惠","打折"], "blacklist": ["广告"]},
    "replace":  {"rules": [{"from": "A", "to": "B", "regex": false}]},
    "format":   {"strip_links": true, "strip_mentions": true, "strip_emoji": false},
    "caption":  {"header": "🔥 转载\\n", "footer": "\\n— @MyChannel"},
    "media":    {"allow": ["photo","video","text"]},
    "length":   {"min": 5, "max": 4000},
    "watermark":{"text": "@MyChannel", "position": "br", "opacity": 128}
}
"""
from __future__ import annotations

from .base import MessageContext, PluginChain, PluginResult
from .registry import build_chain, register, REGISTRY

__all__ = [
    "MessageContext",
    "PluginChain",
    "PluginResult",
    "build_chain",
    "register",
    "REGISTRY",
]
