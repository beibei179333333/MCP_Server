#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""训练模块一 · 指令 1.2：时间窗口内连续消息压缩。

硬约束：
- 按单个 peer（chat_*.json）隔离，禁止跨客户
- 同一 from_id 在窗口内的连续多条 → 空格/逗号合并
- 原文列表保留在 messages_raw，压缩结果在 text_refined

时间窗口：
- 默认 window_max=60s：相邻同发送者消息间隔 ≤60s 视为同一突发段
- window_min=30s：突发段总跨度 ≥30s 或条数≥2 时写入（快速连发跨度<30s 也合并，因仍属窗口内连续）

示例：
  python3 refine_conversation_1_2.py --max-peers 100
  python3 refine_conversation_1_2.py --window-min 30 --window-max 60
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SKILL = Path(__file__).resolve().parent
RAW_DEFAULT = Path("/Users/home/Downloads/tg_private_4y_monthly/00_raw_origin")
SELF_USER_ID = "1335016610"

_INVISIBLE = re.compile(r"[\u200b\u200c\u200d\ufeff\u00a0]")


def extract_text(text: Any) -> str:
    if text is None:
        return ""
    if isinstance(text, str):
        return _INVISIBLE.sub("", text).strip()
    if isinstance(text, list):
        parts = []
        for x in text:
            if isinstance(x, str):
                parts.append(x)
            elif isinstance(x, dict):
                parts.append(str(x.get("text") or ""))
        return _INVISIBLE.sub("", "".join(parts)).strip()
    return _INVISIBLE.sub("", str(text)).strip()


def msg_unix(m: dict) -> int | None:
    u = m.get("date_unixtime")
    if u is not None and str(u).isdigit():
        return int(u)
    d = m.get("date")
    if isinstance(d, str) and "T" in d:
        # 2023-05-25T10:38:41
        try:
            from datetime import datetime

            return int(datetime.fromisoformat(d).timestamp())
        except Exception:
            return None
    return None


def from_id_of(m: dict) -> str:
    fid = m.get("from_id")
    if fid is None:
        return ""
    s = str(fid)
    if s.startswith("user"):
        return s.replace("user", "")
    return s


def pick_joiner(a: str, b: str) -> str:
    """自然连接：空格或逗号。"""
    if not a or not b:
        return ""
    if a[-1] in "，,、。.!！？?…~～:：;；":
        return ""
    # 短词/确认后用逗号更口语
    if len(re.sub(r"\s+", "", a)) <= 4:
        return "，"
    # 纯地址/单号类用空格（仅 ASCII，避免 \w 吃掉中文）
    if re.fullmatch(r"[0-9A-Za-z@./:\-_]+", b.strip()):
        return " "
    return "，"


def compress_texts(texts: list[str]) -> str:
    buf = ""
    for t in texts:
        t = t.strip()
        if not t:
            continue
        if not buf:
            buf = t
            continue
        buf = buf + pick_joiner(buf, t) + t
    return buf.strip()


def iter_valid_messages(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        if m.get("type") == "service":
            continue
        ts = msg_unix(m)
        if ts is None:
            continue
        text = extract_text(m.get("text"))
        if not text:
            continue
        out.append(
            {
                "id": m.get("id"),
                "from_id": from_id_of(m),
                "ts": ts,
                "date": m.get("date"),
                "text": text,
            }
        )
    return out


def burst_groups(
    msgs: list[dict],
    *,
    window_max: int,
) -> list[list[dict]]:
    """同一 from_id 连续消息，相邻间隔 ≤ window_max 归为同一突发段。"""
    if not msgs:
        return []
    groups: list[list[dict]] = []
    cur: list[dict] = [msgs[0]]
    for m in msgs[1:]:
        prev = cur[-1]
        same = m["from_id"] and m["from_id"] == prev["from_id"]
        gap = m["ts"] - prev["ts"]
        if same and 0 <= gap <= window_max:
            cur.append(m)
        else:
            groups.append(cur)
            cur = [m]
    groups.append(cur)
    return groups


def should_keep_burst(group: list[dict], *, window_min: int, window_max: int) -> bool:
    if len(group) < 2:
        return False
    span = group[-1]["ts"] - group[0]["ts"]
    # 落在「窗口定义」内：跨度 ≤ window_max，且（跨度 ≥ window_min 或 条数≥2 的快速连发）
    if span > window_max:
        return False
    # 快速连发（跨度 < window_min）也压缩——仍是窗口内连续输入
    return True


def process_chat(
    path: Path,
    *,
    window_min: int,
    window_max: int,
    self_id: str,
) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    peer_id = str(data.get("id") or path.stem.replace("chat_", ""))
    msgs = iter_valid_messages(data.get("messages") or [])
    # 按时间排序（导出通常已有序）
    msgs.sort(key=lambda x: (x["ts"], x.get("id") or 0))
    rows = []
    for gi, g in enumerate(burst_groups(msgs, window_max=window_max)):
        if not should_keep_burst(g, window_min=window_min, window_max=window_max):
            continue
        texts = [x["text"] for x in g]
        span = g[-1]["ts"] - g[0]["ts"]
        gaps = [g[i]["ts"] - g[i - 1]["ts"] for i in range(1, len(g))]
        role = "self" if str(g[0]["from_id"]) == str(self_id) else "peer"
        rows.append(
            {
                "peer_id": peer_id,
                "burst_id": f"{peer_id}_{g[0]['ts']}_{gi}",
                "from_id": g[0]["from_id"],
                "role": role,
                "t_start": g[0]["ts"],
                "t_end": g[-1]["ts"],
                "span_sec": span,
                "gaps_sec": gaps,
                "n_messages": len(g),
                "message_ids": [x.get("id") for x in g],
                "messages_raw": texts,
                "text_refined": compress_texts(texts),
                "window_min": window_min,
                "window_max": window_max,
                "refine_instruction": "1.2",
                "date_start": g[0].get("date"),
                "date_end": g[-1].get("date"),
            }
        )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Module1 Instruction1.2 time-window compress")
    ap.add_argument("--raw-dir", type=Path, default=RAW_DEFAULT)
    ap.add_argument("--output-dir", type=Path, default=SKILL / "train_data_refined" / "module1_2")
    ap.add_argument("--window-min", type=int, default=30, help="窗口下沿（秒）")
    ap.add_argument("--window-max", type=int, default=60, help="窗口上沿/相邻间隔上限（秒）")
    ap.add_argument("--self-id", default=SELF_USER_ID)
    ap.add_argument("--max-peers", type=int, default=0, help="0=全部联系人")
    ap.add_argument("--role", choices=("all", "self", "peer"), default="all")
    args = ap.parse_args()

    raw_dir = args.raw_dir
    out_dir = args.output_dir if args.output_dir.is_absolute() else SKILL / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "bursts_refined_1_2.jsonl"

    files = sorted(raw_dir.glob("chat_*.json"))
    if args.max_peers:
        files = files[: args.max_peers]

    n_peers = n_bursts = n_msgs = 0
    examples = []
    with out_path.open("w", encoding="utf-8") as fout:
        for fp in files:
            n_peers += 1
            try:
                rows = process_chat(
                    fp,
                    window_min=args.window_min,
                    window_max=args.window_max,
                    self_id=args.self_id,
                )
            except Exception as e:
                fout.write(
                    json.dumps(
                        {"peer_id": fp.stem, "error": str(e), "refine_instruction": "1.2"},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                continue
            for r in rows:
                if args.role != "all" and r["role"] != args.role:
                    continue
                fout.write(json.dumps(r, ensure_ascii=False) + "\n")
                n_bursts += 1
                n_msgs += r["n_messages"]
                if len(examples) < 3 and r["n_messages"] >= 3 and 30 <= r["span_sec"] <= 60:
                    examples.append(
                        {
                            "peer_id": r["peer_id"],
                            "span_sec": r["span_sec"],
                            "messages_raw": r["messages_raw"][:6],
                            "text_refined": r["text_refined"][:200],
                        }
                    )
                elif len(examples) < 3 and r["n_messages"] >= 3:
                    examples.append(
                        {
                            "peer_id": r["peer_id"],
                            "span_sec": r["span_sec"],
                            "messages_raw": r["messages_raw"][:6],
                            "text_refined": r["text_refined"][:200],
                        }
                    )

    report = {
        "instruction": "1.2",
        "module": "conversation_refinement",
        "raw_dir": str(raw_dir),
        "output": str(out_path),
        "peers_scanned": n_peers,
        "bursts_out": n_bursts,
        "messages_compressed": n_msgs,
        "window_min": args.window_min,
        "window_max": args.window_max,
        "role_filter": args.role,
        "examples": examples,
        "principles": "references/training_module_01_refinement.md",
    }
    (out_dir / "report_1_2.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "README.md").write_text(
        "\n".join(
            [
                "# 模块一 · 指令 1.2 产出",
                "",
                f"- 突发段数：{n_bursts}",
                f"- 文件：`{out_path.name}`",
                f"- 窗口：{args.window_min}–{args.window_max}s（相邻间隔 ≤{args.window_max}s）",
                "- 规范：`references/training_module_01_refinement.md`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
