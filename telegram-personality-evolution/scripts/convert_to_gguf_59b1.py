#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 HuggingFace 合并模型转为 GGUF（默认 Q4_K_M，便于本地部署）。

示例：
  python convert_to_gguf.py qwen_beibei_final --outtype q4_k_m

依赖（任选其一）：
  1) 已 clone 的 llama.cpp，且含 convert_hf_to_gguf.py + llama-quantize
  2) 环境变量 LLAMA_CPP_DIR 指向 llama.cpp 根目录
  3) PATH 中有 convert_hf_to_gguf.py / llama-quantize
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _die(msg: str, code: int = 1) -> None:
    print(f"[convert_to_gguf] ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def _which(name: str) -> str | None:
    return shutil.which(name)


def _find_llama_cpp() -> Path | None:
    env = os.environ.get("LLAMA_CPP_DIR")
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env).expanduser().resolve())
    home = Path.home()
    candidates.extend(
        [
            home / "llama.cpp",
            home / "src" / "llama.cpp",
            home / "Downloads" / "llama.cpp",
            Path("/opt/llama.cpp"),
            Path(__file__).resolve().parent / "vendor" / "llama.cpp",
        ]
    )
    for c in candidates:
        if (c / "convert_hf_to_gguf.py").exists():
            return c
        # 新版路径
        if (c / "convert_hf_to_gguf.py").exists():
            return c
    return None


def _find_convert_script(llama_root: Path | None) -> Path:
    if llama_root and (llama_root / "convert_hf_to_gguf.py").exists():
        return llama_root / "convert_hf_to_gguf.py"
    w = _which("convert_hf_to_gguf.py")
    if w:
        return Path(w)
    _die(
        "未找到 convert_hf_to_gguf.py。\n"
        "请 clone https://github.com/ggerganov/llama.cpp 并设置：\n"
        "  export LLAMA_CPP_DIR=/path/to/llama.cpp"
    )
    raise AssertionError


def _find_quantize_bin(llama_root: Path | None) -> str:
    for name in ("llama-quantize", "quantize"):
        w = _which(name)
        if w:
            return w
    if llama_root:
        for rel in (
            "build/bin/llama-quantize",
            "llama-quantize",
            "build/bin/quantize",
            "quantize",
        ):
            p = llama_root / rel
            if p.exists() and os.access(p, os.X_OK):
                return str(p)
    _die(
        "未找到 llama-quantize。请先编译 llama.cpp：\n"
        "  cmake -B build -DGGML_CUDA=OFF && cmake --build build --target llama-quantize -j"
    )
    raise AssertionError


def _normalize_outtype(s: str) -> str:
    # llama-quantize 通常用大写枚举：Q4_K_M
    t = s.strip().replace("-", "_")
    return t.upper()


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert HF model to GGUF Q4_K_M")
    ap.add_argument("model_dir", help="合并后的 HF 模型目录，如 qwen_beibei_final")
    ap.add_argument(
        "--outtype",
        default="q4_k_m",
        help="量化类型，默认 q4_k_m（亦支持 q5_k_m / q8_0 等）",
    )
    ap.add_argument(
        "--outfile",
        default=None,
        help="输出 GGUF 路径；默认 <model_dir>/<name>-<outtype>.gguf",
    )
    ap.add_argument(
        "--keep-f16",
        action="store_true",
        help="保留中间 f16/bf16 GGUF，不删除",
    )
    ap.add_argument("--python", default=sys.executable, help="运行 convert 脚本的 Python")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent
    model_dir = Path(args.model_dir)
    if not model_dir.is_absolute():
        model_dir = (root / model_dir).resolve()

    if not model_dir.exists():
        _die(f"模型目录不存在: {model_dir}\n请先运行 merge_lora.py 生成 qwen_beibei_final。")

    # 粗检 HF 结构
    has_config = (model_dir / "config.json").exists()
    has_weights = any(model_dir.glob("*.safetensors")) or any(model_dir.glob("pytorch_model*.bin"))
    if not (has_config and has_weights):
        _die(
            f"{model_dir} 不像完整 HF 模型（缺 config.json 或权重）。"
            "请确认 merge_lora.py 已成功。"
        )

    outtype = _normalize_outtype(args.outtype)
    llama_root = _find_llama_cpp()
    convert_py = _find_convert_script(llama_root)
    quantize_bin = _find_quantize_bin(llama_root)

    name = model_dir.name
    f16_gguf = model_dir / f"{name}-f16.gguf"
    if args.outfile:
        out_gguf = Path(args.outfile)
        if not out_gguf.is_absolute():
            out_gguf = (root / out_gguf).resolve()
    else:
        out_gguf = model_dir / f"{name}-{outtype.lower()}.gguf"

    print(f"[convert_to_gguf] model={model_dir}")
    print(f"[convert_to_gguf] convert_script={convert_py}")
    print(f"[convert_to_gguf] quantize_bin={quantize_bin}")
    print(f"[convert_to_gguf] outtype={outtype}")
    print(f"[convert_to_gguf] outfile={out_gguf}")

    # Step 1: HF → GGUF (f16)
    cmd1 = [
        args.python,
        str(convert_py),
        str(model_dir),
        "--outfile",
        str(f16_gguf),
        "--outtype",
        "f16",
    ]
    print("[convert_to_gguf] HF → f16 GGUF …")
    print(" ", " ".join(cmd1))
    r1 = subprocess.run(cmd1)
    if r1.returncode != 0:
        _die(f"convert_hf_to_gguf 失败 exit={r1.returncode}")

    # Step 2: quantize
    cmd2 = [quantize_bin, str(f16_gguf), str(out_gguf), outtype]
    print("[convert_to_gguf] quantize …")
    print(" ", " ".join(cmd2))
    r2 = subprocess.run(cmd2)
    if r2.returncode != 0:
        _die(f"llama-quantize 失败 exit={r2.returncode}")

    if not args.keep_f16 and f16_gguf.exists() and f16_gguf != out_gguf:
        f16_gguf.unlink()
        print(f"[convert_to_gguf] removed intermediate {f16_gguf.name}")

    meta = {
        "converted_at": datetime.now(timezone.utc).isoformat(),
        "model_dir": str(model_dir),
        "outtype": outtype,
        "gguf": str(out_gguf),
        "size_bytes": out_gguf.stat().st_size if out_gguf.exists() else None,
        "llama_cpp": str(llama_root) if llama_root else None,
        "script": "convert_to_gguf.py",
    }
    (model_dir / "gguf_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("[convert_to_gguf] DONE")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
