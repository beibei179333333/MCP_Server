#!/usr/bin/env python3
"""构建全联系人宇宙：不过滤汇旺/靓号；≤100 深分析 + 高价值(stars≥3)；价值分层。"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent
PIPE = Path("/Users/home/Downloads/tg_private_4y_monthly")
OUT = SKILL / "outputs" / "contact_universe"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipeline", default=str(PIPE))
    ap.add_argument("--force-rebuild", action="store_true")
    ap.add_argument("--expand-le100", action="store_true", default=True,
                    help="应用 ≤100+高价值 扩量（默认开）")
    args = ap.parse_args()
    pipe = Path(args.pipeline)
    OUT.mkdir(parents=True, exist_ok=True)

    src_script = pipe / "run_full_coverage_upgrade.py"
    univ = pipe / "06_full_coverage" / "contact_universe.json"

    if args.force_rebuild or not univ.exists():
        if not src_script.exists():
            raise SystemExit(f"缺少全覆盖脚本: {src_script}")
        print("running full coverage upgrade…")
        subprocess.check_call([sys.executable, str(src_script)], cwd=str(pipe))

    if args.expand_le100:
        expand = SKILL / "expand_deep_coverage_le100.py"
        if expand.exists():
            print("expanding deep coverage to ≤100 + high-value…")
            subprocess.check_call([sys.executable, str(expand)], cwd=str(SKILL))

    for name in (
        "contact_universe.json",
        "contact_universe_summary.md",
        "deep_priority_le100.jsonl",
        "deep_priority_le50.jsonl",
        "deep_expansion_le100_report.json",
        "POLICY_CONFIRMATION.json",
    ):
        s = pipe / "06_full_coverage" / name
        if s.exists():
            shutil.copy2(s, OUT / name)

    for sub in ("strategies", "short_phrases"):
        s = pipe / "06_full_coverage" / sub
        d = OUT / sub
        if d.is_symlink():
            d.unlink()
        if s.exists() and not d.exists():
            d.symlink_to(s)

    meta = {
        "status": "ready",
        "source": str(univ),
        "deep_priority": str(pipe / "06_full_coverage" / "deep_priority_le100.jsonl"),
        "policy": {
            "filter_huiwang_lianghao": False,
            "deep_analysis_max_messages": 100,
            "deep_analysis_also_high_value_min_stars": 3,
            "full_strategy_for_all": True,
        },
    }
    if univ.exists():
        u = json.loads(univ.read_text(encoding="utf-8"))
        meta["contact_count"] = u.get("contact_count")
        meta["deep_analysis_count"] = u.get("deep_analysis_count")
        meta["deep_analysis_rule"] = u.get("deep_analysis_rule")
        meta["deep_analysis_newly_added"] = u.get("deep_analysis_newly_added")
    (OUT / "build_status.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
