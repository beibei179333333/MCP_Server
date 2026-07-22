#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扩大深分析覆盖：≤50 → ≤100 + 高价值（stars≥3）联系人。

- 更新 contact_universe.json 的 deep_analysis 旗标
- 生成 deep_priority_le100.jsonl（保留 le50 副本只读兼容）
- 同步策略 by_peer 的 deep_analysis 字段（不覆盖策略正文）
- 写出扩量报告供知识库引用
"""
from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PIPE = Path("/Users/home/Downloads/tg_private_4y_monthly")
OUT = PIPE / "06_full_coverage"
SKILL = Path(__file__).resolve().parent
DEEP_MAX = 100
HIGH_VALUE_MIN_STARS = 3  # 特高/超高/高价值


def is_deep(c: dict) -> bool:
    n = int(c.get("valid_message_count") or 0)
    stars = int((c.get("value") or {}).get("stars") or 0)
    return n <= DEEP_MAX or stars >= HIGH_VALUE_MIN_STARS


def main() -> None:
    univ_path = OUT / "contact_universe.json"
    u = json.loads(univ_path.read_text(encoding="utf-8"))
    contacts = u.get("contacts") or []

    # ≤50 基线始终按消息数重算，避免重复跑脚本污染历史字段
    baseline_le50 = sum(1 for c in contacts if int(c.get("valid_message_count") or 0) <= 50)
    old_deep_flag = sum(1 for c in contacts if c.get("deep_analysis"))

    newly = []
    for c in contacts:
        was = bool(c.get("deep_analysis"))
        now = is_deep(c)
        c["deep_analysis"] = now
        c["deep_reason"] = (
            "le100"
            if int(c.get("valid_message_count") or 0) <= DEEP_MAX
            else ("high_value_stars" if now else "none")
        )
        if now and not was:
            newly.append(c)

    deep_n = sum(1 for c in contacts if c.get("deep_analysis"))
    newly_total = max(len(newly), deep_n - int(baseline_le50))
    contacts.sort(
        key=lambda c: (
            0 if c["deep_analysis"] else 1,
            -int((c.get("value") or {}).get("stars") or 0),
            int(c.get("valid_message_count") or 0),
            str(c.get("peer_id")),
        )
    )

    tier = Counter((c.get("value") or {}).get("label") or "?" for c in contacts)
    reason = Counter(c.get("deep_reason") for c in contacts if c.get("deep_analysis"))

    u.update(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contact_count": len(contacts),
            "deep_analysis_count": deep_n,
            "deep_analysis_rule": (
                f"valid_message_count <= {DEEP_MAX} OR value.stars >= {HIGH_VALUE_MIN_STARS}"
            ),
            "deep_analysis_max_messages": DEEP_MAX,
            "high_value_min_stars": HIGH_VALUE_MIN_STARS,
            "deep_analysis_count_prev_le50": int(baseline_le50),
            "deep_analysis_newly_added": int(newly_total),
            "deep_reason_counts": dict(reason),
            "value_tier_counts": dict(tier),
            "contacts": contacts,
            "expansion_note": "2026-07-22 expand deep ≤50→≤100 + high-value stars≥3",
        }
    )
    univ_path.write_text(json.dumps(u, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # deep priority jsonl
    deep_rows = []
    for rank, c in enumerate((x for x in contacts if x.get("deep_analysis")), 1):
        deep_rows.append(
            {
                "priority_rank": rank,
                "peer_id": str(c["peer_id"]),
                "name": c.get("name"),
                "valid_message_count": c.get("valid_message_count"),
                "value": c.get("value"),
                "confidence": c.get("confidence"),
                "relationship_stage": c.get("relationship_stage"),
                "my_attitude": c.get("my_attitude"),
                "deep_analysis": True,
                "deep_reason": c.get("deep_reason"),
                "manual_review_priority": "P0"
                if int(c.get("valid_message_count") or 0) <= 5
                or int((c.get("value") or {}).get("stars") or 0) >= 4
                else "P1",
            }
        )

    le100 = OUT / "deep_priority_le100.jsonl"
    with le100.open("w", encoding="utf-8") as f:
        for row in deep_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # keep le50 as subset snapshot for兼容
    le50 = OUT / "deep_priority_le50.jsonl"
    with le50.open("w", encoding="utf-8") as f:
        r = 0
        for row in deep_rows:
            if int(row.get("valid_message_count") or 0) <= 50:
                r += 1
                row50 = dict(row)
                row50["priority_rank"] = r
                f.write(json.dumps(row50, ensure_ascii=False) + "\n")

    # sync strategy deep flags (text untouched)
    by_peer = OUT / "strategies" / "by_peer"
    patched = 0
    for c in newly:
        pid = str(c["peer_id"])
        sp = by_peer / f"{pid}.json"
        if not sp.exists():
            continue
        rec = json.loads(sp.read_text(encoding="utf-8"))
        rec["deep_analysis"] = True
        rec["deep_reason"] = c.get("deep_reason")
        rec["deep_expanded_at"] = datetime.now(timezone.utc).isoformat()
        for s in (rec.get("strategies") or {}).values():
            if isinstance(s, dict):
                s["deep_analysis"] = True
        sp.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        patched += 1

    # summary md
    md = [
        "# 联系人宇宙清单（全覆盖 · 深分析扩量）",
        "",
        f"- 联系人总数: **{len(contacts)}**（不按汇旺/靓号剔除）",
        f"- 深分析规则: `valid_message_count ≤ {DEEP_MAX}` **或** `value.stars ≥ {HIGH_VALUE_MIN_STARS}`（高价值+）",
        f"- 深分析人数: **{deep_n}**（原 ≤50：**{baseline_le50}**；新增：**{newly_total}**）",
        f"- 深分析构成: {dict(reason)}",
        f"- 价值分布: {dict(tier)}",
        f"- 主队列文件: `deep_priority_le100.jsonl`",
        f"- 兼容副本: `deep_priority_le50.jsonl`（≤50 子集）",
        f"- 策略 deep 旗标已同步: **{patched}**（本轮新标记 {len(newly)}）",
        "",
        "## 硬规则",
        "",
        "1. 不过滤汇旺/靓号联系人，只过滤无效消息",
        "2. 消息越少优先级越高；高价值（stars≥3）即使样本略多也入深分析",
        "3. 禁止仅按高消息量插队",
        "",
    ]
    (OUT / "contact_universe_summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    report = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "deep_max": DEEP_MAX,
        "high_value_min_stars": HIGH_VALUE_MIN_STARS,
        "contact_count": len(contacts),
        "deep_prev_le50": int(baseline_le50),
        "deep_now": deep_n,
        "newly_added": int(newly_total),
        "newly_patched_this_run": len(newly),
        "old_deep_flag_count_before_pass": old_deep_flag,
        "newly_by_range": dict(
            Counter(
                "51-100"
                if 51 <= int(c.get("valid_message_count") or 0) <= 100
                else ("0-50" if int(c.get("valid_message_count") or 0) <= 50 else ">100")
                for c in newly
            )
        )
        or {"51-100": int(newly_total)},
        "deep_reason_counts": dict(reason),
        "strategy_flags_patched": patched,
        "paths": {
            "universe": str(univ_path),
            "deep_le100": str(le100),
            "deep_le50_compat": str(le50),
            "summary": str(OUT / "contact_universe_summary.md"),
        },
    }
    (OUT / "deep_expansion_le100_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    # skill copy
    skill_out = SKILL / "outputs" / "contact_universe"
    skill_out.mkdir(parents=True, exist_ok=True)
    for name in (
        "contact_universe.json",
        "contact_universe_summary.md",
        "deep_priority_le100.jsonl",
        "deep_priority_le50.jsonl",
        "deep_expansion_le100_report.json",
    ):
        s = OUT / name
        if s.exists():
            shutil.copy2(s, skill_out / name)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
