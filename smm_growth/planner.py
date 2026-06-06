"""规划器：根据配置与日期算出「这一天每个频道该下哪些单」。

调度规则（day 为活动第几天，0 起）：
  * 粉丝 members          —— 每天，数量 = 增长曲线(day) × 抖动，按服务上下限裁剪。
  * 浏览 views (AUTO)     —— 每 7 天续单一次（day % 7 == 0），数量 = 每帖目标浏览量。
  * 反应 reactions (AUTO) —— 每 7 天续单一次，数量 = 每帖目标反应数。
  * 评论 comment          —— 每天 daily_qty 条，link 为帖子链接（运行时提供）。
  * 分享 share            —— 每天 daily_qty 次，link 为帖子链接（运行时提供）。
  * 地区粉丝 regional      —— 每 7 天，每个地区 qty_per_region_per_week。
  * Premium 粉丝          —— 每 7 天，qty_per_week。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional

from .config import Campaign, Channel, ServiceGroup

WEEKLY_PERIOD = 7


@dataclass
class PlannedOrder:
    """计划中的一笔下单（尚未真正提交）。"""
    day: int                    # 活动第几天（0 起）
    order_date: date
    category: str               # members / views / reactions / comment / ...
    label: str                  # 备注，例如地区名
    channel: Channel
    group: ServiceGroup         # 含主/备服务，执行时择一
    quantity: int               # 已裁剪到主服务上下限
    link_kind: str              # channel | post

    @property
    def est_cost(self) -> float:
        return self.group.primary.cost(self.quantity)

    @property
    def needs_post_link(self) -> bool:
        return self.link_kind == "post"


def _is_weekly_day(day: int) -> bool:
    return day % WEEKLY_PERIOD == 0


def members_quantity(c: Campaign, day: int, channel: Channel) -> int:
    gc = c.growth("members")
    qty = gc.amount(day, c.duration_days, seed=f"{channel.link}|members|{day}")
    return c.members.primary.clamp(qty)


def views_quantity(c: Campaign, day: int, channel: Channel) -> int:
    gc = c.growth("views_per_post")
    qty = gc.amount(day, c.duration_days, seed=f"{channel.link}|views|{day}")
    return c.views.primary.clamp(qty)


def reactions_quantity(c: Campaign, day: int, channel: Channel) -> int:
    gc = c.growth("reactions_per_post")
    qty = gc.amount(day, c.duration_days, seed=f"{channel.link}|reactions|{day}")
    return c.reactions.primary.clamp(qty)


def orders_for_day(c: Campaign, day: int) -> List[PlannedOrder]:
    """活动第 day 天、所有频道合计应下的单（按频道分组排序）。"""
    if not (0 <= day < c.duration_days):
        return []
    order_date = c.start_date + timedelta(days=day)
    weekly = _is_weekly_day(day)
    out: List[PlannedOrder] = []

    def add(category: str, group: Optional[ServiceGroup], channel: Channel,
            qty: int, label: str = "") -> None:
        if group is None or not group.enabled or qty <= 0:
            return
        out.append(PlannedOrder(
            day=day, order_date=order_date, category=category, label=label,
            channel=channel, group=group, quantity=group.primary.clamp(qty),
            link_kind=group.link_kind,
        ))

    for ch in c.channels:
        # —— 每天 ——
        add("members", c.members, ch, members_quantity(c, day, ch))
        if c.comment:
            add("comment", c.comment, ch, c.comment.fixed_qty or 0)
        if c.share:
            add("share", c.share, ch, c.share.fixed_qty or 0)

        # —— 每 7 天 ——
        if weekly:
            add("views", c.views, ch, views_quantity(c, day, ch))
            add("reactions", c.reactions, ch, reactions_quantity(c, day, ch))
            for rg in c.regional:
                add("regional_members", rg, ch, rg.fixed_qty or 0, label=rg.label)
            if c.premium:
                add("premium_members", c.premium, ch, c.premium.fixed_qty or 0)

    return out


def orders_for_date(c: Campaign, target: date) -> List[PlannedOrder]:
    return orders_for_day(c, c.day_index(target))


def full_schedule(c: Campaign) -> List[PlannedOrder]:
    """整个活动周期（全部天）的所有计划下单。"""
    out: List[PlannedOrder] = []
    for day in range(c.duration_days):
        out.extend(orders_for_day(c, day))
    return out


def total_cost(orders: List[PlannedOrder]) -> float:
    return sum(o.est_cost for o in orders)
