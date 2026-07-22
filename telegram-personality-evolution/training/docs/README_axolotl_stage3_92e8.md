# Axolotl Stage3（全量巩固）

## 命令

```bash
axolotl train config/qwen3.6_27b_full_stage3.yaml \
  --resume_from_checkpoint ./output/qwen_business_stage2
```

## 前置

1. Stage1 → `./output/qwen_personality_stage1`
2. Stage2 → `./output/qwen_business_stage2`（非空 checkpoint）
3. 数据：`train_data_final/{train,val}.jsonl`
4. NVIDIA CUDA + 已安装 `axolotl`

## 本机（Apple Silicon）

不可直接跑：无 CUDA、无 `axolotl`；请把本目录同步到 GPU 机器再训。
