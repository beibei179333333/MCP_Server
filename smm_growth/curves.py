"""渐进增长曲线 + 可复现抖动。

把「第 day 天 / 共 days 天」映射到一个数量（粉丝/浏览/反应…）。曲线从 start 平滑
过渡到 end，可选不同的形状；再叠加一个**确定性**抖动（同样的 channel+day 永远得到
同样的系数），让每天的数字看起来不那么机械，同时计划可复现、可审计。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

SHAPES = ("linear", "ease_in", "ease_out", "s_curve")


def _shape(t: float, curve: str) -> float:
    """把 [0,1] 的进度 t 按曲线形状重映射回 [0,1]。"""
    t = max(0.0, min(1.0, t))
    if curve == "ease_in":          # 慢启动，后期加速
        return t * t
    if curve == "ease_out":         # 快启动，后期放缓
        return 1.0 - (1.0 - t) * (1.0 - t)
    if curve == "s_curve":          # 两头慢中间快（smoothstep）
        return t * t * (3.0 - 2.0 * t)
    return t                        # linear / 未知 -> 线性


def progress(day: int, days: int) -> float:
    """第 day 天（0 起）在总 days 天里的进度，落在 [0,1]。"""
    if days <= 1:
        return 1.0
    return max(0, min(day, days - 1)) / (days - 1)


def curve_value(day: int, days: int, start: float, end: float,
                curve: str = "linear") -> float:
    """连续的曲线取值（未取整、未抖动）。"""
    return start + (end - start) * _shape(progress(day, days), curve)


def jitter_factor(seed: str, pct: float) -> float:
    """根据 seed 得到一个落在 [1-pct, 1+pct] 的确定性系数。

    用 SHA-1 把任意字符串散列成 [0,1) 的伪随机数，所以同一个 seed（例如
    "channel|day"）每次都得到完全相同的系数 —— 计划可复现，便于核对账单。
    """
    if pct <= 0:
        return 1.0
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    unit = (int(digest[:8], 16) % 1_000_000) / 1_000_000.0  # [0,1)
    return 1.0 + (unit * 2.0 - 1.0) * pct


@dataclass
class GrowthCurve:
    """一条增长曲线的参数。"""
    start: float
    end: float
    curve: str = "linear"
    jitter_pct: float = 0.0

    def amount(self, day: int, days: int, seed: str = "") -> int:
        """第 day 天的整数数量（含抖动，向下不低于 0）。"""
        base = curve_value(day, days, self.start, self.end, self.curve)
        val = base * jitter_factor(seed, self.jitter_pct)
        return max(0, int(round(val)))


# 配置里没有给出具体目标时使用的内置默认曲线。
DEFAULT_CURVES = {
    # 每天给每个频道增加的粉丝数：慢启动，30 天累计 ≈ 1100/频道。
    "members": GrowthCurve(start=15, end=60, curve="ease_in", jitter_pct=0.15),
    # AUTO 浏览量：每帖目标浏览数，线性爬升。
    "views_per_post": GrowthCurve(start=200, end=1500, curve="linear", jitter_pct=0.10),
    # AUTO 反应数：每帖目标反应数，线性爬升。
    "reactions_per_post": GrowthCurve(start=20, end=150, curve="linear", jitter_pct=0.10),
}
