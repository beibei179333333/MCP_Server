#!/usr/bin/env python3
"""串行月度 runner：对接主工程与 monthly_agent_tasks 产物，执行评分门禁。"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SKILL = Path(__file__).resolve().parent
PIPE = Path("/Users/home/Downloads/tg_private_4y_monthly")
TASKS = Path("/Users/home/Downloads/压缩包/monthly_agent_tasks_2022-2026-07")
OUT = SKILL / "outputs"
STATE = SKILL / "state" / "month_runner_state.json"


def parse_ym(s: str) -> tuple[int, int]:
    y, m = s.split("-")
    return int(y), int(m)


def ym_dash(y: int, m: int) -> str:
    return f"{y:04d}-{m:02d}"


def ym_compact(y: int, m: int) -> str:
    return f"{y:04d}{m:02d}"


def next_ym(y: int, m: int):
    return (y + 1, 1) if m == 12 else (y, m + 1)


def iter_months(start: str, end: str):
    y, m = parse_ym(start)
    ey, em = parse_ym(end)
    while (y, m) <= (ey, em):
        yield y, m
        y, m = next_ym(y, m)


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"completed": []}


def save_state(st: dict):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    st["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_py(script: Path, args: list[str]):
    cmd = [sys.executable, str(script), *args]
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(SKILL))


def process_month(y: int, m: int) -> dict:
    dash = ym_dash(y, m)
    compact = ym_compact(y, m)
    out_dir = OUT / dash
    out_dir.mkdir(parents=True, exist_ok=True)

    # prefer tasks outputs, else pipeline
    candidates = {
        "report": [
            TASKS / "outputs" / dash / f"report_{dash}.md",
            PIPE / "03_month_feature_tag" / f"{y:04d}" / f"{m:02d}" / f"report_{compact}_month_style.md",
        ],
        "metrics": [
            TASKS / "outputs" / dash / f"metrics_{dash}.json",
            PIPE / "03_month_feature_tag" / f"{y:04d}" / f"{m:02d}" / f"metrics_{compact}_analysis.json",
        ],
        "train": [
            TASKS / "outputs" / dash / f"train_{dash}_alpaca.json",
            PIPE / "05_training_dataset" / f"{y:04d}" / f"{m:02d}" / f"train_{compact}_alpaca.json",
        ],
        "val": [
            TASKS / "outputs" / dash / f"val_{dash}_alpaca.json",
            PIPE / "05_training_dataset" / f"{y:04d}" / f"{m:02d}" / f"val_{compact}_alpaca.json",
        ],
    }
    paths = {}
    for key, opts in candidates.items():
        src = next((p for p in opts if p.exists()), None)
        if not src:
            raise FileNotFoundError(f"{dash} missing {key}: tried {opts}")
        dest = out_dir / f"{key if key!='report' else 'report'}_{dash}{'.md' if key=='report' else '.json' if key=='metrics' else '_alpaca.json' if key in ('train','val') else ''}"
        # normalize names
        if key == "report":
            dest = out_dir / f"report_{dash}.md"
        elif key == "metrics":
            dest = out_dir / f"metrics_{dash}.json"
        elif key == "train":
            dest = out_dir / f"train_{dash}_alpaca.json"
        else:
            dest = out_dir / f"val_{dash}_alpaca.json"
        shutil.copy2(src, dest)
        paths[key] = dest

    # scores
    run_py(SKILL / "score_personality.py", ["--metrics", str(paths["metrics"]), "--out", str(paths["metrics"])])
    run_py(
        SKILL / "score_lora.py",
        ["--train", str(paths["train"]), "--val", str(paths["val"]), "--year", str(y)],
    )

    # ★ 强制产物：月度详细人格总结（22章）
    run_py(SKILL / "generate_monthly_detailed_summary.py", ["--month", dash])
    detailed = SKILL / "reports" / "monthly" / f"{dash}_personality_summary_detailed.md"
    detailed_meta = SKILL / "reports" / "monthly" / f"{dash}_personality_summary_detailed.meta.json"
    if not detailed.exists() or not detailed_meta.exists():
        raise RuntimeError(f"{dash} missing mandatory detailed summary")
    meta = json.loads(detailed_meta.read_text(encoding="utf-8"))
    if not (meta.get("validation") or {}).get("ok"):
        raise RuntimeError(f"{dash} detailed summary validation failed: {meta.get('validation')}")

    # prompt stamp
    prompt = SKILL / "monthly_prompts" / f"{dash}.md"
    status = {
        "year_month": dash,
        "status": "completed",
        "prompt": str(prompt) if prompt.exists() else None,
        "outputs": {k: str(v) for k, v in paths.items()},
        "detailed_summary": str(detailed),
        "detailed_validation": meta.get("validation"),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / f"task_status_{dash}.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # append evolution
    evol = OUT / "long_term_personality_evolution.jsonl"
    metrics = json.loads(paths["metrics"].read_text(encoding="utf-8"))
    with evol.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "year_month": dash,
                    "sample_count": metrics.get("sample_count"),
                    "personality_score": metrics.get("personality_score"),
                    "at": status["completed_at"],
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    return status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2022-01")
    ap.add_argument("--to", dest="end", default="2026-07")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    # ensure universe
    run_py(SKILL / "build_contact_universe.py", [])
    run_py(SKILL / "score_relationship.py", ["--out", str(OUT / "relationship_summary.json")])
    run_py(SKILL / "score_strategy.py", ["--out", str(OUT / "strategy_summary.json")])

    st = load_state()
    completed = set(st.get("completed") or [])
    if args.force:
        completed = set()
        evol = OUT / "long_term_personality_evolution.jsonl"
        if evol.exists():
            evol.unlink()

    for y, m in iter_months(args.start, args.end):
        dash = ym_dash(y, m)
        if dash in completed and not args.force and (OUT / dash / f"report_{dash}.md").exists():
            print(f"skip {dash}")
            continue
        print(f"== {dash} ==")
        status = process_month(y, m)
        print(" ", status["status"])
        completed.add(dash)
        st["completed"] = sorted(completed)
        st["cursor"] = dash
        save_state(st)

    # 55 月全部完成后：强制汇总四年详细演化总报告
    run_py(SKILL / "generate_monthly_detailed_summary.py", ["--final-only"])

    # copy final evolution if exists
    for src in (
        SKILL / "reports" / "final" / "report_2022-01_2026-07_personality_evolution.md",
        TASKS / "report_2022-01_2026-07_personality_evolution.md",
        PIPE / "report_202201_202607_personality_evolution.md",
    ):
        if src.exists():
            shutil.copy2(src, OUT / "report_2022-01_2026-07_personality_evolution.md")
            break

    print(f"DONE months={len(completed)}")


if __name__ == "__main__":
    main()
