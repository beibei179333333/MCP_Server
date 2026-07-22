#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过硅基流动 API 上传微调数据（创建任务须在网页控制台点「开始」）。

硅基流动现状：
- ✅ API 可上传 purpose=fine-tune 的 jsonl
- ❌ 无公开「创建微调任务」REST 接口
- ✅ 训完后用 /v1/chat/completions 调用微调模型

示例：
  python3 upload_siliconflow_finetune.py
  python3 upload_siliconflow_finetune.py --train train_data_siliconflow/train_messages.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import urllib.request

SKILL = Path(__file__).resolve().parent


def load_env() -> None:
    env = SKILL / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def upload_file(api_key: str, path: Path, purpose: str = "fine-tune") -> dict:
    import requests

    url = "https://api.siliconflow.cn/v1/files"
    print(f"[upload] {path} ({path.stat().st_size / 1024 / 1024:.1f} MB)")
    t0 = time.time()
    with path.open("rb") as f:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (path.name, f, "application/jsonl")},
            data={"purpose": purpose},
            timeout=600,
        )
    print(f"[upload] status={r.status_code} elapsed={time.time() - t0:.1f}s")
    r.raise_for_status()
    data = r.json()
    return data.get("data") or data


def main() -> None:
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--train",
        type=Path,
        default=SKILL / "train_data_siliconflow" / "train_messages.jsonl",
    )
    ap.add_argument(
        "--val",
        type=Path,
        default=SKILL / "train_data_siliconflow" / "val_messages.jsonl",
    )
    ap.add_argument("--model", default="Qwen/Qwen2.5-72B-Instruct")
    args = ap.parse_args()

    key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
    if not key:
        print("缺少 SILICONFLOW_API_KEY（写在 .env）", file=sys.stderr)
        raise SystemExit(1)

    train_meta = upload_file(key, args.train)
    val_meta = upload_file(key, args.val)
    result = {
        "base_model": args.model,
        "train_file_id": train_meta.get("id"),
        "val_file_id": val_meta.get("id"),
        "train_file": train_meta,
        "val_file": val_meta,
        "console": "https://cloud.siliconflow.cn/fine-tune",
        "next_steps": [
            "打开控制台 https://cloud.siliconflow.cn/fine-tune",
            "新建对话模型微调",
            f"基础模型选 {args.model}",
            f"训练集选已上传文件 {train_meta.get('id')} / {args.train.name}",
            f"验证集选 {val_meta.get('id')} / {args.val.name}",
            "参数：LR=0.0001 Epochs=2 Batch=8 MaxTokens=4096 LoRA Rank=64 Alpha=64",
            "点击开始微调",
            "完成后：python3 chat_siliconflow.py --model <微调模型ID>",
        ],
    }
    out = SKILL / "train_data_siliconflow" / "upload_api_result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\n>>> 请打开控制台点「开始训练」:", result["console"])


if __name__ == "__main__":
    main()
