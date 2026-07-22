#!/usr/bin/env bash
# 在 NVIDIA CUDA + axolotl 机器上执行
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/5] Stage1 personality (r=128)"
axolotl train config/qwen3.6_27b_personality_stage1.yaml

echo "[2/5] Stage2 business"
axolotl train config/qwen3.6_27b_business_stage2.yaml \
  --resume_from_checkpoint ./output/qwen_personality_stage1

echo "[3/5] Stage3 full + knowledge context"
axolotl train config/qwen3.6_27b_full_stage3.yaml \
  --resume_from_checkpoint ./output/qwen_business_stage2

echo "[4/5] Merge LoRA → full model"
python merge_lora.py \
  --base Qwen/Qwen3-27B \
  --lora output/qwen_full_stage3 \
  --output qwen_beibei_final

echo "[5/5] Quantize → GGUF q4_k_m"
python convert_to_gguf.py qwen_beibei_final --outtype q4_k_m

echo "DONE → ./qwen_beibei_final (+ *.gguf)"
