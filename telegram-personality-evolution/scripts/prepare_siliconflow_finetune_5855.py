#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Alpaca JSONL 转成硅基流动微调所需的 messages JSONL。

硅基流动对话微调要求：
- 每行 JSON，含 messages[{role, content}]
- role ∈ system/user/assistant；system 须在首位
- user/assistant 成对交替

示例：
  python3 prepare_siliconflow_finetune.py \\
    --train train_data_final/train.jsonl \\
    --val train_data_final/val.jsonl \\
    --output-dir train_data_siliconflow \\
    --max-samples 20000 \\
    --max-chars 6000
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

SKILL = Path(__file__).resolve().parent
SEED = 42

DEFAULT_SYSTEM = (
    "你是北北，按长期养成的真实聊天人格回复。"
    "真人化：短句优先，单句约15–30字，适合手机两三行读完；"
    "连续碎句合并成一句流畅话，不写长段落。"
    "留白转化：抛出一句关键信息后停住，等对方回复再往下说，不连发堵话轮。"
    "语气：自然口语，绝不能像AI或教科书；专业、有说服力，带经验感和亲和力，不端着也不讨好。"
    "被动商务，少模板广告腔；共情有配额；不越权、不帮收验证码。"
)


def alpaca_to_messages(row: dict, *, system: str, max_chars: int) -> dict | None:
    instruction = (row.get("instruction") or "").strip()
    inp = (row.get("input") or "").strip()
    out = (row.get("output") or "").strip()
    if not out:
        return None
    if inp and instruction:
        user = f"{instruction}\n\n{inp}"
    elif inp:
        user = inp
    else:
        user = instruction
    user = user.strip()
    if not user:
        return None
    if len(user) > max_chars:
        user = user[: max_chars - 20] + "\n…(截断)"
    if len(out) > max_chars:
        out = out[: max_chars - 20] + "\n…(截断)"
    out_obj: dict = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": out},
        ]
    }
    # 分块隔离元数据（单客户/单会话）；平台可读 messages，额外字段便于审计
    did = row.get("dialog_id") or row.get("peer_id")
    if not did:
        # knowledge 等无 dialog 时仍给唯一会话键，避免混块
        did = f"knowledge_{hash((user[:80], out[:80])) & 0xFFFFFFFF:08x}"
    out_obj["dialog_id"] = did
    if row.get("peer_id"):
        out_obj["peer_id"] = row["peer_id"]
    if row.get("year_month"):
        out_obj["year_month"] = row["year_month"]
    return out_obj


def load_rows(path: Path, *, max_samples: int | None, prefer_knowledge: bool) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    random.Random(SEED).shuffle(rows)
    if prefer_knowledge:
        rows.sort(key=lambda r: 0 if r.get("from_knowledge") else 1)
    if max_samples and len(rows) > max_samples:
        # 保底塞进 knowledge，再补其余
        know = [r for r in rows if r.get("from_knowledge")]
        rest = [r for r in rows if not r.get("from_knowledge")]
        take = know[: max_samples // 10] + rest
        rows = take[:max_samples]
    return rows


def write_jsonl(rows: list[dict], out: Path, *, system: str, max_chars: int) -> int:
    n = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            msg = alpaca_to_messages(r, system=system, max_chars=max_chars)
            if not msg:
                continue
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
            n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=Path, default=SKILL / "train_data_final" / "train.jsonl")
    ap.add_argument("--val", type=Path, default=SKILL / "train_data_final" / "val.jsonl")
    ap.add_argument("--knowledge", type=Path, default=SKILL / "train_data_knowledge" / "context.jsonl")
    ap.add_argument("--output-dir", type=Path, default=SKILL / "train_data_siliconflow")
    ap.add_argument("--max-samples", type=int, default=20000, help="训练条数上限（控费用）")
    ap.add_argument("--max-val", type=int, default=1000)
    ap.add_argument("--max-chars", type=int, default=6000, help="单侧文本截断，适配平台 Max Tokens≤4096")
    ap.add_argument("--system", default=DEFAULT_SYSTEM)
    ap.add_argument("--include-knowledge", action="store_true", default=True)
    args = ap.parse_args()

    random.seed(SEED)
    out_dir = args.output_dir if args.output_dir.is_absolute() else SKILL / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    train_rows = load_rows(args.train, max_samples=args.max_samples, prefer_knowledge=True)
    if args.include_knowledge and args.knowledge.exists():
        krows = [json.loads(l) for l in args.knowledge.open() if l.strip()]
        # 去重追加 knowledge
        train_rows = krows + train_rows
        # 再截断
        if len(train_rows) > args.max_samples:
            train_rows = train_rows[: args.max_samples]

    val_rows = load_rows(args.val, max_samples=args.max_val, prefer_knowledge=False)

    train_path = out_dir / "train_messages.jsonl"
    val_path = out_dir / "val_messages.jsonl"
    n_train = write_jsonl(train_rows, train_path, system=args.system, max_chars=args.max_chars)
    n_val = write_jsonl(val_rows, val_path, system=args.system, max_chars=args.max_chars)

    manifest = {
        "format": "siliconflow-messages-jsonl",
        "base_model_recommended": "Qwen/Qwen2.5-72B-Instruct",
        "note": "硅基流动当前可微调最强对话模型为 Qwen2.5-72B-Instruct；LoRA Rank 平台上限 64",
        "train": str(train_path),
        "val": str(val_path),
        "train_n": n_train,
        "val_n": n_val,
        "suggested_hyperparams": {
            "learning_rate": 0.0001,
            "n_epochs": 2,
            "batch_size": 8,
            "max_tokens": 4096,
            "lora_rank": 64,
            "lora_alpha": 64,
            "lora_dropout": 0.05,
            "profile": "效果优先/高容量长期记忆（平台 rank 上限 64）",
        },
        "console": "https://cloud.siliconflow.cn/fine-tune",
        "ak": "https://cloud.siliconflow.cn/me/account/ak",
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "UPLOAD.md").write_text(
        "\n".join(
            [
                "# 硅基流动微调上传说明",
                "",
                "## 模型",
                "",
                "选平台支持微调的最强对话模型：`Qwen/Qwen2.5-72B-Instruct`",
                "",
                "## 文件",
                "",
                f"- 训练集：`{train_path.name}`（{n_train} 条）",
                f"- 验证集：`{val_path.name}`（{n_val} 条）",
                "",
                "## 步骤",
                "",
                "1. 打开 https://cloud.siliconflow.cn/fine-tune",
                "2. 新建「对话模型微调」",
                "3. 基础模型选 `Qwen/Qwen2.5-72B-Instruct`",
                "4. 上传本目录两个 jsonl",
                "5. 参数建议：LR=0.0001，Epochs=2，Batch=8，MaxTokens=4096，LoRA Rank=64，Alpha=64",
                "6. 开始微调；完成后在控制台复制模型 ID",
                "7. 本机调用：",
                "",
                "```bash",
                "python3 chat_siliconflow.py --model <你的微调模型ID>",
                "```",
                "",
                "说明：本机 M4 Pro（24GB）无法本地训练 72B；训练在硅基流动云端完成，训后用 API 在电脑上调用。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
