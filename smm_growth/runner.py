"""执行器：把某一天的计划真正下单（或 dry-run 演练）。

行为：
  * 按频道分组下单；同频道内每单间隔 delay_between_orders 秒，频道之间间隔
    delay_between_channels 秒（dry-run 下不真正 sleep）。
  * 主服务失败时自动切换到备用服务再试。
  * 需要帖子链接的服务（评论/分享）若没有提供对应频道的帖子链接，则跳过并告警。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from .config import Campaign
from .panel import OrderResult, PanelClient, build_clients
from .planner import PlannedOrder, orders_for_date


@dataclass
class RunReport:
    target_date: date
    dry_run: bool
    results: List[OrderResult] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)

    @property
    def placed(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.ok)

    @property
    def total_cost(self) -> float:
        return sum(r.cost for r in self.results if r.ok)


def _place(order: PlannedOrder, link: str, clients: Dict[str, PanelClient],
           verbose: bool) -> OrderResult:
    """对一笔计划下单尝试主服务，失败则尝试备用服务，返回最后结果。"""
    last: Optional[OrderResult] = None
    for i, spec in enumerate(order.specs or order.group.candidates()):
        client = clients.get(spec.panel)
        if client is None:
            last = OrderResult(ok=False, panel=spec.panel, service_id=spec.service_id,
                               link=link, quantity=order.quantity,
                               error=f"未知面板 {spec.panel!r}")
            continue
        qty = spec.clamp(order.quantity)
        extra = None
        # 自定义评论服务需要 comments 文本；这里没有文案来源，跳过自定义、用随机评论服务。
        res = client.add(spec.service_id, link, qty, cost=spec.cost(qty), extra=extra)
        if res.ok:
            if i > 0 and verbose:
                print(f"    （主服务失败，已切换备用服务 {spec.service_id}）", flush=True)
            return res
        last = res
        if verbose:
            print(f"    服务 {spec.service_id} 失败：{res.error}", flush=True)
    return last  # type: ignore[return-value]


def run_date(c: Campaign, target: date, *,
             clients: Optional[Dict[str, PanelClient]] = None,
             post_links: Optional[Dict[str, str]] = None,
             only: Optional[List[str]] = None,
             channel_filter: Optional[str] = None,
             dry_run: Optional[bool] = None,
             verbose: bool = True) -> RunReport:
    """执行某一天的下单计划。

    参数：
      clients      —— 面板名→客户端；缺省按配置自动构建。
      post_links   —— 频道链接→帖子链接，供评论/分享使用。
      only         —— 只执行这些类别（members/views/...）。
      channel_filter — 只处理链接/名称包含该子串的频道。
      dry_run      —— 覆盖配置里的 execution.dry_run（None 表示沿用配置）。
    """
    effective_dry = c.execution.dry_run if dry_run is None else dry_run
    if clients is None:
        clients = build_clients(c, dry_run=effective_dry, verbose=verbose)
    post_links = post_links or {}
    report = RunReport(target_date=target, dry_run=effective_dry)

    if not c.in_range(target):
        report.skipped.append(
            f"{target} 不在活动周期内（{c.start_date} 起共 {c.duration_days} 天）")
        return report

    orders = orders_for_date(c, target)
    if only:
        wanted = set(only)
        orders = [o for o in orders if o.category in wanted]
    if channel_filter:
        cf = channel_filter.lower()
        orders = [o for o in orders
                  if cf in o.channel.link.lower() or cf in o.channel.name.lower()]

    # 按频道分组，便于控制频道间隔
    by_channel: Dict[str, List[PlannedOrder]] = {}
    for o in orders:
        by_channel.setdefault(o.channel.link, []).append(o)

    ex = c.execution
    for ci, (ch_link, ch_orders) in enumerate(by_channel.items()):
        ch_name = ch_orders[0].channel.name
        if verbose:
            print(f"\n▶ 频道 {ch_name}  ({ch_link})", flush=True)
        for oi, order in enumerate(ch_orders):
            # 决定下单链接
            if order.needs_post_link:
                link = post_links.get(order.channel.link)
                if not link:
                    report.skipped.append(
                        f"{order.category}@{ch_name}：缺帖子链接，跳过")
                    if verbose:
                        print(f"  - 跳过 {order.category}（未提供帖子链接）", flush=True)
                    continue
            else:
                link = order.channel.link

            res = _place(order, link, clients, verbose)
            report.results.append(res)
            if verbose:
                print("  " + res.summary(), flush=True)

            if not effective_dry and oi < len(ch_orders) - 1:
                time.sleep(ex.delay_between_orders)

        if not effective_dry and ci < len(by_channel) - 1:
            time.sleep(ex.delay_between_channels)

    return report


def load_post_links(path: str) -> Dict[str, str]:
    """从文件读取「频道链接 帖子链接」映射（每行一对，空格/逗号/制表符分隔）。"""
    out: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p for p in line.replace(",", " ").split() if p]
            if len(parts) >= 2:
                out[parts[0]] = parts[1]
    return out
