#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用硅基流动 API 做推理冒烟 / 调用微调后模型。

API Key 从 .env 的 SILICONFLOW_API_KEY 读取（勿把 Key 写进代码）。

示例：
  python3 chat_siliconflow.py --prompt "在吗"
  python3 chat_siliconflow.py --model Qwen/Qwen2.5-72B-Instruct --prompt "对方询价能量，怎么回"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

SKILL = Path(__file__).resolve().parent


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def chat(base_url: str, api_key: str, model: str, prompt: str, system: str) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 1024,
        "stream": False,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"]


def main() -> None:
    load_env(SKILL / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--model",
        default=os.environ.get("SILICONFLOW_CHAT_MODEL", "Qwen/Qwen2.5-72B-Instruct"),
    )
    ap.add_argument("--prompt", default="用一两句介绍你会怎么跟人聊天（短、碎、实）。")
    ap.add_argument(
        "--system",
        default=(
            "你是北北，按真实聊天人格回复：短句15–30字、手机两三行可读；"
            "抛一句关键信息后留白等回复；自然口语绝无AI腔；"
            "专业有说服力，有经验感和亲和力；实、有边界。"
        ),
    )
    ap.add_argument(
        "--base-url",
        default=os.environ.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"),
    )
    args = ap.parse_args()
    key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
    if not key:
        print("缺少 SILICONFLOW_API_KEY，请写入 .env", file=sys.stderr)
        raise SystemExit(1)
    print(f"[chat] model={args.model}")
    text = chat(args.base_url, key, args.model, args.prompt, args.system)
    print(text)


if __name__ == "__main__":
    main()
