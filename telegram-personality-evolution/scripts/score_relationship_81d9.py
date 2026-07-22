#!/usr/bin/env python3
"""关系成长轴评分：relationship_stage + my_attitude 分布校验。"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

STAGES = [
    "陌生", "初识", "建立信任", "熟悉", "合作", "长期", "淡化", "失联", "恢复联系", "结束",
]
ATTITUDES = ["主动", "被动", "平衡", "冷处理", "拒绝", "高投入", "低投入"]


def summarize_universe(universe_path: Path) -> dict:
    u = json.loads(universe_path.read_text(encoding="utf-8"))
    stages = Counter()
    attitudes = Counter()
    deep = 0
    for c in u.get("contacts") or []:
        stages[c.get("relationship_stage") or "陌生"] += 1
        attitudes[c.get("my_attitude") or "被动"] += 1
        if c.get("deep_analysis"):
            deep += 1
    return {
        "contact_count": u.get("contact_count"),
        "deep_analysis_count": deep,
        "relationship_stage_dist": dict(stages),
        "my_attitude_dist": dict(attitudes),
        "unknown_stages": [k for k in stages if k not in STAGES],
        "unknown_attitudes": [k for k in attitudes if k not in ATTITUDES],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--universe",
        default="/Users/home/Downloads/tg_private_4y_monthly/06_full_coverage/contact_universe.json",
    )
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    summary = summarize_universe(Path(args.universe))
    if args.out:
        Path(args.out).write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
