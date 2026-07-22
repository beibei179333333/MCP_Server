#!/usr/bin/env python3
"""LoRA 月度数据集校验：空 output、权重、dialog_id、train/val 泄漏。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

WEIGHTS = {
    2022: {"高营养Top20%": 1.69, "中营养60%": 1.3, "低营养20%": 0.78},
    2023: {"高营养Top20%": 1.56, "中营养60%": 1.2, "低营养20%": 0.72},
    2024: {"高营养Top20%": 1.3, "中营养60%": 1.0, "低营养20%": 0.6},
    2025: {"高营养Top20%": 1.3, "中营养60%": 1.0, "低营养20%": 0.6},
    2026: {"高营养Top20%": 1.17, "中营养60%": 0.9, "低营养20%": 0.54},
}


def score_lora(train_path: Path, val_path: Path, year: int) -> dict:
    train = json.loads(train_path.read_text(encoding="utf-8"))
    val = json.loads(val_path.read_text(encoding="utf-8")) if val_path.exists() else []
    errors = []
    ids = []
    for split_name, rows in (("train", train), ("val", val)):
        for r in rows:
            ids.append((split_name, r.get("dialog_id")))
            if not (r.get("output") or "").strip():
                errors.append(f"{split_name}:{r.get('dialog_id')}:empty_output")
            if '"type": "service"' in json.dumps(r, ensure_ascii=False):
                errors.append(f"{split_name}:{r.get('dialog_id')}:service")
            lvl = r.get("nutrition_level")
            sw = r.get("sample_weight")
            expect = WEIGHTS.get(year, {}).get(lvl)
            if expect is not None and sw is not None and abs(float(sw) - float(expect)) > 1e-6:
                # allow pipeline temporal*nutrition recomputed; check formula if fields present
                tw = r.get("temporal_weight")
                nm = r.get("nutrition_multiplier")
                if tw is not None and nm is not None:
                    calc = round(float(tw) * float(nm), 4)
                    if abs(float(sw) - calc) > 1e-6:
                        errors.append(f"{split_name}:{r.get('dialog_id')}:weight_mismatch")

    # dialog unique within month (train+val)
    all_ids = [i for _, i in ids if i]
    if len(all_ids) != len(set(all_ids)):
        errors.append("duplicate_dialog_id")

    # peer leakage
    def peers(rows):
        return {r.get("peer_id") for r in rows if r.get("peer_id")}

    # peer_id may be absent in alpaca; skip if missing
    tr_p = peers(train)
    va_p = peers(val)
    leak = tr_p & va_p if tr_p and va_p else set()
    if leak:
        errors.append(f"peer_leak:{len(leak)}")

    return {
        "train_n": len(train),
        "val_n": len(val),
        "year": year,
        "errors": errors[:50],
        "error_count": len(errors),
        "ok": len(errors) == 0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True)
    ap.add_argument("--val", required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    result = score_lora(Path(args.train), Path(args.val), args.year)
    if args.out:
        Path(args.out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 2)


if __name__ == "__main__":
    main()
