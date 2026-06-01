"""Anti-fraud risk check for a single Telegram account.

This is a *defensive* helper: given one account's public/group metadata (the
same fields the export pipeline already collects), it produces a transparent,
heuristic **risk indicator** — meant to help a user decide whether a
counterparty they are about to deal with looks like a likely scam / spam /
marketing account.

It deliberately does NOT try to uncover a person's real-world identity,
location, linked accounts, or any private information. Every point in the score
is explained, and the output carries a disclaimer: it is a heuristic signal
based on public metadata and the data source's own scam/fake flags, not a
verdict on a real person, and not a substitute for your own due diligence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .filters import FilterConfig, _EMOJI_RE, _PHONE_RE, _URL_RE, _RANDOM_UN_RE
from .models import Member


# Risk levels, ordered, with their Chinese labels.
LEVELS = {
    "high": "高风险",
    "medium": "可疑",
    "low": "低风险",
    "unknown": "未知（未查到该账号）",
}

DISCLAIMER = (
    "⚠️ 说明：这是基于公开/群组元数据与数据源标记的【启发式风险提示】，"
    "用于判断对方是否像诈骗/营销/垃圾账号，帮助你防范被骗。"
    "它不是对某个真实人物身份的认定，也不能替代你自己的尽职调查；"
    "请勿用于骚扰、人肉或追踪他人。"
)


@dataclass
class Signal:
    """One explained contribution to the assessment."""
    kind: str          # "risk" | "ok" | "info"
    weight: int        # risk points contributed (can be negative for "ok")
    label: str         # human-readable, Chinese


@dataclass
class RiskReport:
    account: str
    found: bool = False
    level: str = "unknown"
    score: int = 0
    signals: List[Signal] = field(default_factory=list)
    # Minimal identity echo so the user knows which account was checked.
    username: str = ""
    display_name: str = ""

    @property
    def level_label(self) -> str:
        return LEVELS.get(self.level, self.level)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "account": self.account,
            "found": self.found,
            "level": self.level,
            "level_label": self.level_label,
            "score": self.score,
            "username": self.username,
            "display_name": self.display_name,
            "signals": [
                {"kind": s.kind, "weight": s.weight, "label": s.label}
                for s in self.signals
            ],
            "disclaimer": DISCLAIMER,
        }


# Score thresholds (after summing risk-point weights, when not hard-flagged).
_HIGH_THRESHOLD = 4
_MEDIUM_THRESHOLD = 2
# An account considered "established" (a mild reassuring signal).
_ESTABLISHED_MESSAGES = 50


def assess(member: Optional[Member], cfg: Optional[FilterConfig] = None) -> RiskReport:
    """Assess one account and return an explained :class:`RiskReport`."""
    cfg = cfg or FilterConfig()

    if member is None:
        return RiskReport(account="", found=False, level="unknown")

    account = member.username and f"@{member.username}" or member.user_id or member.full_name
    report = RiskReport(
        account=account,
        found=True,
        username=member.username,
        display_name=member.full_name,
    )
    signals = report.signals

    # --- hard flags from the data source ----------------------------------
    if member.is_scam:
        signals.append(Signal("risk", 100, "数据源已将该账号标记为 scam（诈骗）"))
    if member.is_fake:
        signals.append(Signal("risk", 100, "数据源已将该账号标记为 fake（仿冒）"))

    # --- promotional / spam heuristics (reuse the export ad-detection) -----
    blob = " ".join(x for x in (member.username, member.full_name, member.bio) if x)
    kw_hits = sorted({
        kw for kw in cfg.keywords() if kw and kw in blob.lower()
    })
    if kw_hits:
        shown = "、".join(kw_hits[:6]) + ("…" if len(kw_hits) > 6 else "")
        signals.append(Signal("risk", min(len(kw_hits), 3),
                              f"名称/简介含广告营销关键词（{shown}）"))
    if _URL_RE.search(blob):
        signals.append(Signal("risk", 2, "名称/简介里带推广链接或外部 @handle"))
    if _PHONE_RE.search(member.full_name) or _PHONE_RE.search(member.bio):
        signals.append(Signal("risk", 2, "名称/简介里写了联系电话（典型营销特征）"))
    if len(_EMOJI_RE.findall(member.full_name)) >= cfg.emoji_limit:
        signals.append(Signal("risk", 1, "昵称堆叠大量 emoji（常见于营销号）"))

    # --- weak / anonymous account signals ----------------------------------
    if not member.username:
        signals.append(Signal("risk", 1, "没有设置用户名（匿名，较难追溯/核实）"))
    elif _RANDOM_UN_RE.match(member.username):
        signals.append(Signal("risk", 1, f"用户名像系统随机生成（{member.username}）"))
    if member.has_photo is False:
        signals.append(Signal("risk", 1, "没有头像（新号/小号常见特征）"))
    if member.is_bot:
        signals.append(Signal("info", 1, "这是一个 bot（机器人）账号，注意辨别用途"))

    # --- reassuring signals -------------------------------------------------
    if member.is_verified:
        signals.append(Signal("ok", -100, "账号通过官方认证（verified）"))
    if member.is_premium:
        signals.append(Signal("ok", -1, "Telegram Premium 会员（开通需付费，门槛略高）"))
    if member.message_count >= _ESTABLISHED_MESSAGES:
        signals.append(Signal("ok", -1,
                              f"在群里发言较多（{member.message_count} 条），不像一次性小号"))
    if member.has_photo is True:
        signals.append(Signal("ok", 0, "设置了头像"))

    # --- aggregate ----------------------------------------------------------
    score = sum(s.weight for s in signals)
    report.score = max(score, 0)

    if member.is_scam or member.is_fake:
        report.level = "high"
    elif member.is_verified:
        # Officially verified: cap at low, but any spam signals stay visible.
        report.level = "low"
    elif score >= _HIGH_THRESHOLD:
        report.level = "high"
    elif score >= _MEDIUM_THRESHOLD:
        report.level = "medium"
    else:
        report.level = "low"

    return report


def format_report(report: RiskReport) -> str:
    """Render a :class:`RiskReport` as a human-readable block of text."""
    icon = {"high": "🛑", "medium": "⚠️", "low": "✅", "unknown": "❓"}[report.level]
    lines = [
        "===== 账号风险核查 =====",
        f"查询对象 : {report.account}",
    ]
    if not report.found:
        lines.append(f"结果     : {icon} {report.level_label}")
        lines.append("（数据源里没有这个账号的记录，无法给出风险判断。）")
        lines.append("")
        lines.append(DISCLAIMER)
        return "\n".join(lines)

    if report.display_name:
        lines.append(f"昵称     : {report.display_name}")
    lines.append(f"风险等级 : {icon} {report.level_label}（评分 {report.score}）")

    risks = [s for s in report.signals if s.kind == "risk"]
    oks = [s for s in report.signals if s.kind == "ok"]
    infos = [s for s in report.signals if s.kind == "info"]
    if risks:
        lines.append("风险信号 :")
        lines.extend(f"  - {s.label}" for s in risks)
    if infos:
        lines.append("提示     :")
        lines.extend(f"  - {s.label}" for s in infos)
    if oks:
        lines.append("正面信号 :")
        lines.extend(f"  + {s.label}" for s in oks)
    if not risks and not infos:
        lines.append("（未发现明显的诈骗/营销风险信号。）")

    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)
