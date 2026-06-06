"""命令行入口。

示例
----
  # 看整套 30 天计划的汇总（总单数、各类数量、预计花费）
  python -m smm_growth plan --summary

  # 看某一天 / 第 N 天具体要下哪些单
  python -m smm_growth plan --date 2026-06-02
  python -m smm_growth plan --day 0

  # 把整套计划导出成 CSV（逐单）
  python -m smm_growth plan --csv schedule.csv

  # 演练今天的下单（dry-run，不真正花钱）
  python -m smm_growth run --date 2026-06-02

  # 真正下单（覆盖配置里的 dry_run）；评论/分享需提供帖子链接
  python -m smm_growth run --date 2026-06-02 --execute --posts posts.txt

  # 查询各面板余额 / 查询订单状态
  python -m smm_growth balance
  python -m smm_growth status --panel smmfollows --order 12345 --order 12346
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import List, Optional

from .config import Campaign, load_campaign
from .panel import build_clients
from .planner import PlannedOrder, full_schedule, orders_for_day, total_cost
from .runner import load_post_links, run_date


def _parse_date(s: Optional[str]) -> date:
    if not s:
        return date.today()
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


def _resolve_day(c: Campaign, args) -> int:
    if getattr(args, "day", None) is not None:
        return args.day
    return c.day_index(_parse_date(getattr(args, "date", None)))


# ----------------------------------------------------------------------------- plan
def _print_orders(orders: List[PlannedOrder]) -> None:
    for o in orders:
        kind = "帖子" if o.needs_post_link else "频道"
        lbl = f"/{o.label}" if o.label else ""
        print(f"  {o.category:17}{lbl:9} qty={o.quantity:<7} "
              f"[{kind}] svc={o.group.primary.service_id:<6} "
              f"≈${o.est_cost:.4f}  {o.channel.name}")


def cmd_plan(args) -> int:
    c = load_campaign(args.config)

    if args.summary:
        sched = full_schedule(c)
        by_cat: dict = defaultdict(lambda: [0, 0, 0.0])  # 单数, 数量, 花费
        for o in sched:
            row = by_cat[o.category]
            row[0] += 1
            row[1] += o.quantity
            row[2] += o.est_cost
        print(f"活动：{c.start_date} 起 {c.duration_days} 天，"
              f"{len(c.channels)} 个频道，每天 {c.posts_per_day} 帖")
        print(f"{'类别':<20}{'单数':>8}{'总数量':>12}{'预计花费($)':>16}")
        print("-" * 56)
        for cat in sorted(by_cat):
            n, qty, cost = by_cat[cat]
            print(f"{cat:<20}{n:>8}{qty:>12}{cost:>16.4f}")
        print("-" * 56)
        print(f"{'合计':<20}{len(sched):>8}{'':>12}{total_cost(sched):>16.4f}")
        print("\n注：浏览/反应为 AUTO 服务，每 7 天续单一次；数量为「每帖目标值」，"
              "实际计费随面板订阅而定，这里为名义估算。")
        return 0

    day = _resolve_day(c, args)
    if not (0 <= day < c.duration_days):
        print(f"该日期不在活动周期内（第 {day} 天，有效范围 0..{c.duration_days - 1}）",
              file=sys.stderr)
        return 1
    when = c.start_date + timedelta(days=day)
    orders = orders_for_day(c, day)
    print(f"第 {day} 天（{when}）共 {len(orders)} 笔下单，预计 ${total_cost(orders):.4f}：")
    _print_orders(orders)

    if args.csv:
        _write_schedule_csv(full_schedule(c) if args.all else orders, args.csv)
        print(f"\n已写出 CSV：{args.csv}")
    return 0


def _write_schedule_csv(orders: List[PlannedOrder], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["day", "date", "category", "label", "channel", "channel_link",
                    "link_kind", "panel", "service_id", "quantity", "est_cost_usd"])
        for o in orders:
            w.writerow([o.day, o.order_date, o.category, o.label, o.channel.name,
                        o.channel.link, o.link_kind, o.group.primary.panel,
                        o.group.primary.service_id, o.quantity,
                        f"{o.est_cost:.4f}"])


# ----------------------------------------------------------------------------- run
def cmd_run(args) -> int:
    c = load_campaign(args.config)
    target = _parse_date(args.date)
    dry = None
    if args.execute:
        dry = False
    elif args.dry_run:
        dry = True

    post_links = load_post_links(args.posts) if args.posts else None
    only = [s.strip() for s in args.only.split(",")] if args.only else None

    report = run_date(c, target, post_links=post_links, only=only,
                      channel_filter=args.channel, dry_run=dry, verbose=not args.quiet)

    print("\n===== 执行汇总 =====")
    print(f"日期        : {report.target_date}  ({'DRY-RUN 演练' if report.dry_run else '真实下单'})")
    print(f"成功下单    : {report.placed}")
    print(f"失败        : {report.failed}")
    print(f"成功花费(估): ${report.total_cost:.4f}")
    if report.skipped:
        print(f"跳过 {len(report.skipped)} 项：")
        for s in report.skipped[:20]:
            print(f"  - {s}")
    return 0 if report.failed == 0 else 2


# ----------------------------------------------------------------------------- balance/status
def cmd_balance(args) -> int:
    c = load_campaign(args.config)
    clients = build_clients(c, dry_run=False, verbose=False)
    for name, client in clients.items():
        if not client.panel.has_key:
            print(f"{name:<12} (未设置 API key，跳过)")
            continue
        data = client.balance()
        if isinstance(data, dict) and data.get("balance") is not None:
            print(f"{name:<12} 余额 {data.get('balance')} {data.get('currency', '')}")
        else:
            print(f"{name:<12} 查询失败：{data}")
    return 0


def cmd_status(args) -> int:
    c = load_campaign(args.config)
    clients = build_clients(c, dry_run=False, verbose=False)
    client = clients.get(args.panel)
    if client is None:
        print(f"未知面板 {args.panel!r}（可选：{', '.join(clients)}）", file=sys.stderr)
        return 1
    print(client.status(list(args.order)))
    return 0


# ----------------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="smm_growth",
        description="Telegram SMM 自动增长引擎：按配置与增长曲线自动下单。",
    )
    p.add_argument("--config", help="YAML 配置路径（默认 smm_growth/campaign.yaml）。")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("plan", help="查看下单计划（不下单）。")
    pl.add_argument("--date", help="目标日期 YYYY-MM-DD（默认今天）。")
    pl.add_argument("--day", type=int, help="活动第几天（0 起），与 --date 二选一。")
    pl.add_argument("--summary", action="store_true", help="打印整套 30 天汇总。")
    pl.add_argument("--csv", help="把计划逐单写出为 CSV。")
    pl.add_argument("--all", action="store_true",
                    help="配合 --csv：导出整套周期而非单日。")
    pl.set_defaults(func=cmd_plan)

    rn = sub.add_parser("run", help="执行某一天的下单（默认 dry-run）。")
    rn.add_argument("--date", help="目标日期 YYYY-MM-DD（默认今天）。")
    rn.add_argument("--execute", action="store_true",
                    help="真正下单（覆盖配置里的 dry_run=true）。")
    rn.add_argument("--dry-run", action="store_true", help="强制演练，不下单。")
    rn.add_argument("--posts", help="帖子链接文件（频道链接 帖子链接，每行一对）。")
    rn.add_argument("--only", help="只执行这些类别，逗号分隔（如 members,views）。")
    rn.add_argument("--channel", help="只处理名称/链接包含该子串的频道。")
    rn.add_argument("--quiet", action="store_true", help="减少日志。")
    rn.set_defaults(func=cmd_run)

    ba = sub.add_parser("balance", help="查询各面板余额。")
    ba.set_defaults(func=cmd_balance)

    st = sub.add_parser("status", help="查询订单状态。")
    st.add_argument("--panel", required=True, help="面板名（如 smmfollows）。")
    st.add_argument("--order", action="append", required=True,
                    help="订单号（可重复）。")
    st.set_defaults(func=cmd_status)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
