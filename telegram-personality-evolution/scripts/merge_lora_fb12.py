#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 LoRA adapter 合并进基座模型并保存为完整权重。

示例：
  python merge_lora.py \\
    --base Qwen/Qwen3-27B \\
    --lora output/qwen_full_stage3 \\
    --output qwen_beibei_final
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _die(msg: str, code: int = 1) -> None:
    print(f"[merge_lora] ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def _find_adapter_dir(lora_path: Path) -> Path:
    """支持直接指向 adapter 目录，或含 checkpoint-* 的训练输出目录。"""
    if (lora_path / "adapter_config.json").exists():
        return lora_path
    if (lora_path / "adapter_model.safetensors").exists() or (
        lora_path / "adapter_model.bin"
    ).exists():
        return lora_path

    checkpoints = sorted(
        [p for p in lora_path.glob("checkpoint-*") if p.is_dir()],
        key=lambda p: int(p.name.split("-")[-1]) if p.name.split("-")[-1].isdigit() else -1,
    )
    for ckpt in reversed(checkpoints):
        if (ckpt / "adapter_config.json").exists() or (
            ckpt / "adapter_model.safetensors"
        ).exists():
            return ckpt

    # Axolotl 有时把 adapter 放在根目录子路径
    for cand in [lora_path / "adapter_model", lora_path]:
        if (cand / "adapter_config.json").exists():
            return cand

    _die(
        f"未在 {lora_path} 找到 LoRA adapter（需要 adapter_config.json）。"
        "请先完成 Stage3 训练产出 output/qwen_full_stage3。"
    )
    raise AssertionError  # unreachable


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge LoRA into base model")
    ap.add_argument("--base", required=True, help="基座模型 ID 或本地路径，如 Qwen/Qwen3-27B")
    ap.add_argument("--lora", required=True, help="LoRA 目录，如 output/qwen_full_stage3")
    ap.add_argument("--output", required=True, help="合并后输出目录，如 qwen_beibei_final")
    ap.add_argument("--dtype", default="bfloat16", choices=("bfloat16", "float16", "float32"))
    ap.add_argument("--device-map", default="auto", help="accelerate device_map，默认 auto")
    ap.add_argument("--trust-remote-code", action="store_true", default=True)
    ap.add_argument("--max-shard-size", default="5GB")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent
    lora_path = Path(args.lora)
    if not lora_path.is_absolute():
        lora_path = (root / lora_path).resolve()
    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = (root / out_path).resolve()

    if not lora_path.exists():
        _die(f"LoRA 路径不存在: {lora_path}")

    adapter_dir = _find_adapter_dir(lora_path)
    print(f"[merge_lora] base={args.base}")
    print(f"[merge_lora] lora={adapter_dir}")
    print(f"[merge_lora] output={out_path}")

    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as e:
        _die(
            f"缺少依赖: {e}\n"
            "请安装: pip install 'transformers>=4.45' peft accelerate torch safetensors"
        )

    dtype_map = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }
    torch_dtype = dtype_map[args.dtype]

    print("[merge_lora] loading tokenizer …")
    tokenizer = AutoTokenizer.from_pretrained(
        args.base, trust_remote_code=args.trust_remote_code
    )

    print("[merge_lora] loading base model …")
    base = AutoModelForCausalLM.from_pretrained(
        args.base,
        torch_dtype=torch_dtype,
        device_map=args.device_map,
        trust_remote_code=args.trust_remote_code,
    )

    print("[merge_lora] loading LoRA adapter …")
    model = PeftModel.from_pretrained(base, str(adapter_dir))

    print("[merge_lora] merge_and_unload …")
    model = model.merge_and_unload()

    out_path.mkdir(parents=True, exist_ok=True)
    print(f"[merge_lora] saving merged model → {out_path}")
    model.save_pretrained(str(out_path), max_shard_size=args.max_shard_size)
    tokenizer.save_pretrained(str(out_path))

    meta = {
        "merged_at": datetime.now(timezone.utc).isoformat(),
        "base": args.base,
        "lora": str(adapter_dir),
        "output": str(out_path),
        "dtype": args.dtype,
        "script": "merge_lora.py",
    }
    (out_path / "merge_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("[merge_lora] DONE")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    # 降低 tokenizer 并行告警噪声
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    main()
