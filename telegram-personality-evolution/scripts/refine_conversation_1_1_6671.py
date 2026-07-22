#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""训练模块一 · 指令 1.1：单次会话句子合并与精简。

硬约束：
- 只处理单条样本内文本（已按 dialog 隔离），禁止跨 dialog/peer
- 原文写入 *_raw，精炼写入 *_refined，不覆盖存证
- 每句目标 15–30 字；口语流畅，避免机器翻译感

示例：
  python3 refine_conversation_1_1.py \\
    --input train_data_final/train.jsonl \\
    --output-dir train_data_refined/module1_1 \\
    --max-rows 5000
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SKILL = Path(__file__).resolve().parent

_SEP = re.compile(r"^[\s\-—_=✨💎🎫✅🎁💰⚡️📌・·]+$")
_SPACE = re.compile(r"\s+")
_TEMPLATE_HINT = (
    "代开会员",
    "秒开【",
    "自动回复",
    "闪兑TRX",
    "能量闪租",
    "汇旺账号",
)


def _is_break_line(s: str) -> bool:
    t = s.strip()
    if not t:
        return True
    if _SEP.fullmatch(t):
        return True
    if set(t) <= set("-—_=~＊*・· "):
        return True
    return False


def _looks_template(s: str) -> bool:
    return any(h in s for h in _TEMPLATE_HINT)

def char_len(s: str) -> int:
    """长度：汉字=1，其它非空白=1。"""
    s = _SPACE.sub("", s)
    return len(s)


def split_utterances(text: str) -> list[str]:
    if not text:
        return []
    parts = []
    for line in text.replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        # 同一行里按句号/问号/叹号再切（过长时）
        chunks = re.split(r"(?<=[。！？!?])", line)
        for c in chunks:
            c = c.strip()
            if c:
                parts.append(c)
    return parts


def _pick_joiner(a: str, b: str) -> str:
    if not a or not b:
        return ""
    # 已有标点结尾则直接拼
    if a[-1] in "，,、。.!！？?…~～":
        return ""
    # 短确认后接下文，用逗号更口语
    if char_len(a) <= 4:
        return "，"
    return ""


def merge_to_target(
    utterances: list[str],
    *,
    min_len: int = 15,
    max_len: int = 30,
) -> list[str]:
    """贪心合并连续短句，使每句落在 [min_len, max_len]。

    分隔线 / 装饰行作为硬边界；模板广告块内只做行内截断，不跨价目乱拼。
    """
    if not utterances:
        return []

    # 分段：遇分隔线切开
    segments: list[list[str]] = [[]]
    for u in utterances:
        u = u.strip()
        if not u:
            continue
        if _is_break_line(u):
            if segments[-1]:
                segments.append([])
            continue
        segments[-1].append(u)
    segments = [s for s in segments if s]

    out: list[str] = []
    for seg in segments:
        # 模板块：按行独立，超长再切，不跨行合并价目
        if any(_looks_template(x) for x in seg):
            for u in seg:
                if char_len(u) <= max_len:
                    out.append(u)
                else:
                    out.extend(_split_long(u, max_len=max_len))
            continue
        out.extend(_merge_segment(seg, min_len=min_len, max_len=max_len))
    return [x.strip() for x in out if x.strip()]


def _merge_segment(
    atoms_in: list[str],
    *,
    min_len: int,
    max_len: int,
) -> list[str]:
    atoms: list[str] = []
    for u in atoms_in:
        if char_len(u) <= max_len:
            atoms.append(u)
        else:
            atoms.extend(_split_long(u, max_len=max_len))

    out: list[str] = []
    buf = ""
    for u in atoms:
        u = u.strip()
        if not u:
            continue
        if not buf:
            buf = u
            continue
        joined = buf + _pick_joiner(buf, u) + u
        if char_len(joined) <= max_len:
            buf = joined
            continue
        if char_len(buf) >= min_len:
            out.append(buf)
            buf = u
        else:
            merged = buf + _pick_joiner(buf, u) + u
            pieces = _split_long(merged, max_len=max_len)
            for i, p in enumerate(pieces):
                if i < len(pieces) - 1:
                    out.append(p)
                else:
                    buf = p
    if buf:
        if char_len(buf) < min_len and out:
            cand = out[-1] + _pick_joiner(out[-1], buf) + buf
            if char_len(cand) <= max_len:
                out[-1] = cand
            else:
                out.append(buf)
        else:
            out.append(buf)
    return out

def _split_long(text: str, *, max_len: int) -> list[str]:
    text = text.strip()
    if char_len(text) <= max_len:
        return [text]
    # 优先在逗号、顿号处切
    parts: list[str] = []
    buf = ""
    for ch in text:
        trial = buf + ch
        if char_len(trial) <= max_len:
            buf = trial
            if ch in "，,、;； " and char_len(buf) >= 15:
                parts.append(buf.strip())
                buf = ""
            continue
        if buf:
            parts.append(buf.strip())
        buf = ch
    if buf.strip():
        parts.append(buf.strip())
    return [p for p in parts if p]


def refine_side(text: str, *, min_len: int = 15, max_len: int = 30) -> tuple[str, dict]:
    utt = split_utterances(text)
    refined_list = merge_to_target(utt, min_len=min_len, max_len=max_len)
    refined = "\n".join(refined_list)
    meta = {
        "utterances_in": len(utt),
        "utterances_out": len(refined_list),
        "merged": max(0, len(utt) - len(refined_list)),
        "lens": [char_len(x) for x in refined_list],
        "out_of_range": sum(1 for x in refined_list if not (min_len <= char_len(x) <= max_len)),
    }
    return refined, meta


def refine_row(row: dict, *, min_len: int, max_len: int, sides: str) -> dict:
    out = dict(row)
    out["input_raw"] = row.get("input") or ""
    out["output_raw"] = row.get("output") or ""
    meta: dict = {"module": "1.1", "dialog_id": row.get("dialog_id")}

    if sides in ("both", "input"):
        ri, mi = refine_side(out["input_raw"], min_len=min_len, max_len=max_len)
        out["input_refined"] = ri
        # 训练默认用精炼 input（可切回 raw）
        out["input"] = ri
        meta["input"] = mi
    if sides in ("both", "output"):
        ro, mo = refine_side(out["output_raw"], min_len=min_len, max_len=max_len)
        out["output_refined"] = ro
        out["output"] = ro
        meta["output"] = mo

    out["refine_meta"] = meta
    out["refine_instruction"] = "1.1"
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Module1 Instruction1.1 conversation refine")
    ap.add_argument("--input", type=Path, default=SKILL / "train_data_final" / "train.jsonl")
    ap.add_argument("--output-dir", type=Path, default=SKILL / "train_data_refined" / "module1_1")
    ap.add_argument("--max-rows", type=int, default=0, help="0=全部")
    ap.add_argument("--min-len", type=int, default=15)
    ap.add_argument("--max-len", type=int, default=30)
    ap.add_argument("--sides", choices=("both", "input", "output"), default="both")
    ap.add_argument("--skip-knowledge", action="store_true", default=True)
    args = ap.parse_args()

    inp = args.input if args.input.is_absolute() else SKILL / args.input
    out_dir = args.output_dir if args.output_dir.is_absolute() else SKILL / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "train_refined_1_1.jsonl"

    n_in = n_out = 0
    sum_merged = 0
    oor = 0
    examples = []

    with inp.open(encoding="utf-8") as fin, out_path.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            n_in += 1
            if args.max_rows and n_out >= args.max_rows:
                break
            row = json.loads(line)
            if args.skip_knowledge and (
                row.get("from_knowledge") or str(row.get("dialog_id", "")).startswith("knowledge")
            ):
                continue
            # 分块隔离：必须有 dialog_id
            if not row.get("dialog_id"):
                continue
            refined = refine_row(row, min_len=args.min_len, max_len=args.max_len, sides=args.sides)
            fout.write(json.dumps(refined, ensure_ascii=False) + "\n")
            n_out += 1
            meta = refined.get("refine_meta") or {}
            for side in ("input", "output"):
                if side in meta:
                    sum_merged += int(meta[side].get("merged") or 0)
                    oor += int(meta[side].get("out_of_range") or 0)
            if len(examples) < 3 and (meta.get("output") or {}).get("merged", 0) > 0:
                raw_o = refined.get("output_raw", "")
                if not _looks_template(raw_o):
                    examples.append(
                        {
                            "dialog_id": refined.get("dialog_id"),
                            "output_raw": raw_o[:180],
                            "output_refined": refined.get("output_refined", "")[:180],
                        }
                    )

    report = {
        "instruction": "1.1",
        "module": "conversation_refinement",
        "source": str(inp),
        "output": str(out_path),
        "rows_in_scanned": n_in,
        "rows_out": n_out,
        "merge_ops_total": sum_merged,
        "sentences_out_of_range": oor,
        "min_len": args.min_len,
        "max_len": args.max_len,
        "sides": args.sides,
        "examples": examples,
        "principles": "references/training_module_01_refinement.md",
    }
    (out_dir / "report_1_1.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "README.md").write_text(
        "\n".join(
            [
                "# 模块一 · 指令 1.1 产出",
                "",
                f"- 样本数：{n_out}",
                f"- 文件：`{out_path.name}`",
                "- 字段：`input_raw`/`output_raw` + `input_refined`/`output_refined`；训练用 `input`/`output` 已替换为精炼版",
                "- 规范：`references/training_module_01_refinement.md`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
