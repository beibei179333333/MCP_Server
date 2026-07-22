#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验训练样本是否违反「分块隔离」：单样本不得混多 dialog / 多 peer 痕迹。"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

PEER_HINT = re.compile(r"(?:peer[_\s-]?id|chat[_\s-]?)(\d{5,})", re.I)


def check_file(path: Path, limit: int | None = None) -> dict:
    n = 0
    missing_dialog = 0
    dup_dialog = 0
    multi_peer_hint = 0
    seen: dict[str, int] = {}
    examples = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if limit is not None and n >= limit:
                break
            line = line.strip()
            if not line:
                continue
            n += 1
            row = json.loads(line)
            did = str(row.get("dialog_id") or "")
            if not did and "messages" in row:
                # siliconflow 行：用 messages 结构视为单会话；无 dialog_id 记 warning 但不算混客户
                did = f"messages_row_{n}"
            if not row.get("dialog_id") and "messages" not in row:
                missing_dialog += 1
                if len(examples) < 5:
                    examples.append({"issue": "missing_dialog_id", "row_n": n})
            elif row.get("dialog_id"):
                seen[did] = seen.get(did, 0) + 1
            text = f"{row.get('input','')}\n{row.get('output','')}"
            if "messages" in row:
                text = "\n".join(
                    str(m.get("content") or "") for m in (row.get("messages") or [])
                )
            peers = set(PEER_HINT.findall(text))
            # knowledge / meta samples may lack peer — OK
            if len(peers) > 1:
                multi_peer_hint += 1
                if len(examples) < 8:
                    examples.append(
                        {
                            "issue": "multi_peer_hint_in_text",
                            "dialog_id": did,
                            "peers": sorted(peers),
                        }
                    )
    dup_dialog = sum(1 for v in seen.values() if v > 1)
    return {
        "file": str(path),
        "n": n,
        "missing_dialog_id": missing_dialog,
        "duplicate_dialog_id_count": dup_dialog,
        "multi_peer_hint_in_text": multi_peer_hint,
        "ok": missing_dialog == 0 and multi_peer_hint == 0,
        "examples": examples,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--files",
        nargs="*",
        default=[
            "train_data_final/train.jsonl",
            "train_data_final/val.jsonl",
            "train_data_siliconflow/train_messages.jsonl",
        ],
    )
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    root = Path(__file__).resolve().parent
    reports = []
    for rel in args.files:
        p = root / rel if not Path(rel).is_absolute() else Path(rel)
        if not p.exists():
            reports.append({"file": str(p), "ok": False, "error": "missing"})
            continue
        reports.append(check_file(p, limit=args.limit))
    print(json.dumps({"isolation_check": reports}, ensure_ascii=False, indent=2))
    if any(not r.get("ok") for r in reports):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
