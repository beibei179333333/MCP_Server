"""加载并校验 YAML 增长配置。

设计要点：
  * API key 绝不写进仓库。配置值里支持 ``${VAR}`` 与 ``${VAR:-默认值}`` 形式的环境变量
    插值；提交到 git 的 campaign.yaml 用 ``${SMMFOLLOWS_API_KEY}`` 这样的占位符。
  * 解析成带类型的 dataclass，方便规划器/执行器与单元测试使用。
  * 配置里没给出增长目标时，回退到 curves.DEFAULT_CURVES。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import yaml

from .curves import DEFAULT_CURVES, GrowthCurve

# 默认配置文件路径（相对仓库根目录）。
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "campaign.yaml")

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def interpolate_env(value: str, environ: Optional[Dict[str, str]] = None) -> str:
    """把字符串里的 ``${VAR}`` / ``${VAR:-default}`` 替换成环境变量值。

    未设置且没给默认值时替换为空字符串（dry-run 下足够用，真正下单前需设好环境变量）。
    """
    env = environ if environ is not None else os.environ

    def repl(m: "re.Match[str]") -> str:
        name, default = m.group(1), m.group(2)
        if name in env:
            return env[name]
        return default if default is not None else ""

    return _ENV_PATTERN.sub(repl, value)


def _interp_tree(node: Any, environ: Optional[Dict[str, str]]) -> Any:
    """对整棵配置树里的字符串做环境变量插值。"""
    if isinstance(node, str):
        return interpolate_env(node, environ)
    if isinstance(node, dict):
        return {k: _interp_tree(v, environ) for k, v in node.items()}
    if isinstance(node, list):
        return [_interp_tree(v, environ) for v in node]
    return node


# ----------------------------------------------------------------------------- 数据结构
@dataclass
class Panel:
    name: str
    url: str
    key: str

    @property
    def has_key(self) -> bool:
        return bool(self.key and self.key.strip())


@dataclass
class ServiceSpec:
    """单个 SMM 服务（面板上的一个 service id）。"""
    panel: str
    service_id: int
    description: str
    rate_per_1k: float = 0.0
    min_order: int = 1
    max_order: int = 1_000_000
    is_auto: bool = False

    def clamp(self, qty: int) -> int:
        return max(self.min_order, min(self.max_order, qty))

    def cost(self, qty: int) -> float:
        return qty / 1000.0 * self.rate_per_1k


@dataclass
class ServiceGroup:
    """一类服务：主服务 + 可选备用服务，附带调度信息。

    link_kind:
      * "channel" —— 下单时 link = 频道链接（粉丝、AUTO 浏览/反应、地区/Premium 粉丝）。
      * "post"    —— 下单时 link = 具体帖子链接（评论、分享），运行时需提供帖子链接。
    schedule: "daily"（每天）| "weekly"（每 7 天，即 day % 7 == 0）。
    """
    category: str
    primary: ServiceSpec
    backup: Optional[ServiceSpec] = None
    enabled: bool = True
    schedule: str = "daily"
    link_kind: str = "channel"
    fixed_qty: Optional[int] = None          # 评论/分享/地区/Premium 这类固定数量
    label: str = ""                          # 例如地区名 chinese/russian…

    def candidates(self) -> List[ServiceSpec]:
        out = [self.primary]
        if self.backup is not None:
            out.append(self.backup)
        return out


@dataclass
class Channel:
    name: str
    link: str


@dataclass
class Execution:
    dry_run: bool = True
    delay_between_orders: float = 3.0
    delay_between_channels: float = 10.0
    max_retries: int = 3
    retry_delay: float = 5.0


@dataclass
class Campaign:
    start_date: date
    duration_days: int
    posts_per_day: int
    channels: List[Channel]
    panels: Dict[str, Panel]
    execution: Execution
    # 主力服务
    members: ServiceGroup
    views: ServiceGroup
    reactions: ServiceGroup
    # 辅助服务
    comment: Optional[ServiceGroup] = None
    share: Optional[ServiceGroup] = None
    regional: List[ServiceGroup] = field(default_factory=list)
    premium: Optional[ServiceGroup] = None
    # 增长曲线（缺省回退到 DEFAULT_CURVES）
    curves: Dict[str, GrowthCurve] = field(default_factory=dict)

    def day_index(self, target: date) -> int:
        """目标日期对应的活动第几天（0 起）。可能为负或越界。"""
        return (target - self.start_date).days

    def in_range(self, target: date) -> bool:
        d = self.day_index(target)
        return 0 <= d < self.duration_days

    def panel(self, name: str) -> Panel:
        if name not in self.panels:
            raise KeyError(f"配置里没有名为 {name!r} 的面板")
        return self.panels[name]

    def growth(self, key: str) -> GrowthCurve:
        return self.curves.get(key) or DEFAULT_CURVES[key]


# ----------------------------------------------------------------------------- 解析
def _to_date(v: Any) -> date:
    if isinstance(v, date):
        return v
    return datetime.strptime(str(v).strip(), "%Y-%m-%d").date()


def _spec(panel: str, raw: Dict[str, Any]) -> ServiceSpec:
    return ServiceSpec(
        panel=raw.get("panel", panel),
        service_id=int(raw["service_id"]),
        description=str(raw.get("description", "")),
        rate_per_1k=float(raw.get("rate_per_1k", 0.0)),
        min_order=int(raw.get("min_order", 1)),
        max_order=int(raw.get("max_order", 1_000_000)),
        is_auto=bool(raw.get("is_auto", False)),
    )


def _pair(category: str, raw: Dict[str, Any], **extra: Any) -> ServiceGroup:
    """从 {primary:{...}, backup:{...}} 解析出一个 ServiceGroup。"""
    primary_raw = raw["primary"]
    backup_raw = raw.get("backup")
    return ServiceGroup(
        category=category,
        primary=_spec(primary_raw.get("panel", ""), primary_raw),
        backup=_spec(backup_raw.get("panel", ""), backup_raw) if backup_raw else None,
        **extra,
    )


def _curve(raw: Optional[Dict[str, Any]], default: GrowthCurve) -> GrowthCurve:
    if not raw:
        return default
    return GrowthCurve(
        start=float(raw.get("start", default.start)),
        end=float(raw.get("end", default.end)),
        curve=str(raw.get("curve", default.curve)),
        jitter_pct=float(raw.get("jitter_pct", default.jitter_pct)),
    )


def parse_campaign(data: Dict[str, Any]) -> Campaign:
    """把（已插值的）配置 dict 解析成 Campaign。"""
    panels = {
        name: Panel(name=name, url=str(p["url"]).rstrip("/"), key=str(p.get("key", "")))
        for name, p in (data.get("panels") or {}).items()
    }
    channels = [Channel(name=str(c["name"]), link=str(c["link"]))
                for c in (data.get("channels") or [])]

    services = data.get("services") or {}
    members = _pair("members", services["members"], link_kind="channel", schedule="daily")
    views = _pair("views", services["views"], link_kind="channel", schedule="weekly")
    reactions = _pair("reactions", services["reactions"], link_kind="channel",
                      schedule="weekly")

    addons = data.get("addon_services") or {}

    comment = None
    if "comment" in addons:
        c = addons["comment"]
        comment = _pair("comment", c, enabled=bool(c.get("enabled", True)),
                        link_kind="post", schedule="daily",
                        fixed_qty=int(c.get("daily_qty", 0)))

    share = None
    if "share" in addons:
        s = addons["share"]
        share = _pair("share", s, enabled=bool(s.get("enabled", True)),
                      link_kind="post", schedule="daily",
                      fixed_qty=int(s.get("daily_qty", 0)))

    regional: List[ServiceGroup] = []
    if "regional_members" in addons:
        rm = addons["regional_members"]
        if rm.get("enabled", True):
            per = int(rm.get("qty_per_region_per_week", 0))
            for region, raw in (rm.get("regions") or {}).items():
                regional.append(ServiceGroup(
                    category="regional_members",
                    primary=_spec(raw.get("panel", ""), raw),
                    enabled=True, schedule="weekly", link_kind="channel",
                    fixed_qty=per, label=region,
                ))

    premium = None
    if "premium_members" in addons:
        pm = addons["premium_members"]
        if pm.get("enabled", True):
            premium = _pair("premium_members", pm, enabled=True, schedule="weekly",
                            link_kind="channel", fixed_qty=int(pm.get("qty_per_week", 0)))

    ex = data.get("execution") or {}
    execution = Execution(
        dry_run=bool(ex.get("dry_run", True)),
        delay_between_orders=float(ex.get("delay_between_orders", 3)),
        delay_between_channels=float(ex.get("delay_between_channels", 10)),
        max_retries=int(ex.get("max_retries", 3)),
        retry_delay=float(ex.get("retry_delay", 5)),
    )

    g = data.get("growth") or {}
    curves = {
        "members": _curve(g.get("members"), DEFAULT_CURVES["members"]),
        "views_per_post": _curve(g.get("views_per_post"),
                                 DEFAULT_CURVES["views_per_post"]),
        "reactions_per_post": _curve(g.get("reactions_per_post"),
                                     DEFAULT_CURVES["reactions_per_post"]),
    }

    return Campaign(
        start_date=_to_date(data["start_date"]),
        duration_days=int(data.get("duration_days", 30)),
        posts_per_day=int(data.get("posts_per_day", 0)),
        channels=channels,
        panels=panels,
        execution=execution,
        members=members, views=views, reactions=reactions,
        comment=comment, share=share, regional=regional, premium=premium,
        curves=curves,
    )


def load_campaign(path: Optional[str] = None,
                  environ: Optional[Dict[str, str]] = None) -> Campaign:
    """从 YAML 文件加载配置（含环境变量插值）。"""
    path = path or DEFAULT_CONFIG_PATH
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    raw = _interp_tree(raw, environ)
    return parse_campaign(raw)
