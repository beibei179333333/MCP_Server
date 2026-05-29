"""纯逻辑：关键词匹配 + 点击去重 / 冷却。

这部分不依赖 OCR / 鼠标 / GUI，可以离线单元测试，
所以监控的「大脑」是可验证的，最关键的部分不靠运气。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple


@dataclass
class OcrBox:
    """一段被识别出来的文字及其在屏幕上的包围盒。

    box = (left, top, width, height)，均为屏幕绝对像素坐标。
    """

    text: str
    box: Tuple[int, int, int, int]
    confidence: float = 1.0

    @property
    def center(self) -> Tuple[int, int]:
        l, t, w, h = self.box
        return (l + w // 2, t + h // 2)


@dataclass
class Hit:
    """一次命中：哪个关键词、在哪段文字里、点击坐标是多少。"""

    keyword: str
    text: str
    x: int
    y: int
    confidence: float


def find_hits(
    boxes: Iterable[OcrBox],
    keywords: Sequence[str],
    min_confidence: float = 0.0,
) -> List[Hit]:
    """在 OCR 结果里找出包含任意关键词的文字段，返回命中列表。

    匹配大小写不敏感（对英文关键词友好），中文不受影响。
    """
    norm_keywords = [(k, k.strip().lower()) for k in keywords if k and k.strip()]
    hits: List[Hit] = []
    for b in boxes:
        if b.confidence < min_confidence:
            continue
        haystack = (b.text or "").lower()
        if not haystack:
            continue
        for original, kw in norm_keywords:
            if kw and kw in haystack:
                cx, cy = b.center
                hits.append(
                    Hit(keyword=original, text=b.text, x=cx, y=cy, confidence=b.confidence)
                )
                break  # 一段文字命中一个关键词即可，不重复记
    return hits


class KeywordMatcher:
    """对一批 OCR 结果做关键词匹配的小封装。"""

    def __init__(self, keywords: Sequence[str], min_confidence: float = 0.0):
        self.keywords = list(keywords)
        self.min_confidence = min_confidence

    def match(self, boxes: Iterable[OcrBox]) -> List[Hit]:
        return find_hits(boxes, self.keywords, self.min_confidence)


class ClickGuard:
    """点击去重 / 冷却，避免同一个「领取」按钮被反复连点。

    规则：
    - 全局冷却：上一次点击后 `cooldown` 秒内，原则上不再点。
    - 位置去重：在冷却时间内，若新命中点与最近点过的点距离 < `dedupe_radius`，
      视为「还是那一个按钮」，跳过。
    - 超过冷却时间后，记忆清空，可以再次点击（比如出现了新一条领取）。
    """

    def __init__(self, cooldown: float = 8.0, dedupe_radius: int = 45):
        self.cooldown = cooldown
        self.dedupe_radius = dedupe_radius
        self._recent: List[Tuple[float, int, int]] = []  # (时间戳, x, y)

    def _prune(self, now: float) -> None:
        self._recent = [
            (t, x, y) for (t, x, y) in self._recent if now - t < self.cooldown
        ]

    def should_click(self, x: int, y: int, now: float) -> bool:
        """判断此刻点 (x, y) 是否放行。放行则记录下来。"""
        self._prune(now)
        for _, px, py in self._recent:
            if math.hypot(x - px, y - py) <= self.dedupe_radius:
                return False  # 还是最近点过的那个位置，跳过
        if self._recent:
            return False  # 冷却期内、且不是同一位置 —— 仍按冷却节流，稍后再点
        self._recent.append((now, x, y))
        return True

    def record(self, x: int, y: int, now: float) -> None:
        """外部已执行点击时，手动登记一次（一般 should_click 已自动登记）。"""
        self._recent.append((now, x, y))

    def reset(self) -> None:
        self._recent.clear()


def pick_best(hits: Sequence[Hit]) -> Optional[Hit]:
    """多个命中时挑一个最该点的：优先置信度最高的。"""
    if not hits:
        return None
    return max(hits, key=lambda h: h.confidence)
