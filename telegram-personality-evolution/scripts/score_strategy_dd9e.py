#!/usr/bin/env python3
"""策略覆盖评分：校验全员 12 类策略 + confidence 字段。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED = [
    "利益捆绑",
    "长期关系经营",
    "战略价值整合",
    "战略撤退",
    "筹码对调",
    "情绪杠杆",
    "沉没成本",
    "情报商",
    "框架驯兽",
    "规则降维",
    "流失挽回",
    "风险审核",
]


def score_strategies(jsonl_path: Path) -> dict:
    total = 0
    missing_types = 0
    missing_conf = 0
    deep = 0
    low_conf = 0
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            total += 1
            o = json.loads(line)
            if o.get("deep_analysis"):
                deep += 1
            conf = o.get("confidence")
            if conf is None:
                missing_conf += 1
            elif conf < 0.45:
                low_conf += 1
            st = o.get("strategies") or {}
            for t in REQUIRED:
                if t not in st:
                    missing_types += 1
                    break
    return {
        "strategy_file": str(jsonl_path),
        "contacts_scored": total,
        "deep_analysis_contacts": deep,
        "missing_strategy_type_rows": missing_types,
        "missing_confidence_rows": missing_conf,
        "low_confidence_rows": low_conf,
        "required_types": REQUIRED,
        "ok": missing_types == 0 and missing_conf == 0 and total > 0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--jsonl",
        default="/Users/home/Downloads/tg_private_4y_monthly/06_full_coverage/strategies/all_contacts_strategies.jsonl",
    )
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    result = score_strategies(Path(args.jsonl))
    if args.out:
        Path(args.out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 2)


if __name__ == "__main__":
    main()
