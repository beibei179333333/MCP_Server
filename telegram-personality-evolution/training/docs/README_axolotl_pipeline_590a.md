# Axolotl 三阶段 + 合并（r=128 · knowledge 上下文）

## 数据

| 集 | 路径 |
|---|---|
| 全量 HQ | `train_data_final/{train,val}.jsonl` |
| 商务 Stage2 | `train_data_business_stage2/{train,val}.jsonl` |
| knowledge 额外上下文 | `train_data_knowledge/context.jsonl` |

由 `prepare_training_data.py --add-knowledge` 生成。

## LoRA

- `lora_r: 128`（强化长期记忆容量）
- `lora_alpha: 64`
- **不可**与旧 `r=64` checkpoint 混用，须从 Stage1 重训

## 命令（NVIDIA CUDA）

```bash
# Stage1 人格
axolotl train config/qwen3.6_27b_personality_stage1.yaml

# Stage2 商务
axolotl train config/qwen3.6_27b_business_stage2.yaml \
  --resume_from_checkpoint ./output/qwen_personality_stage1

# Stage3 全量巩固
axolotl train config/qwen3.6_27b_full_stage3.yaml \
  --resume_from_checkpoint ./output/qwen_business_stage2

# 最终合并模型（二选一）
axolotl merge-lora config/qwen3.6_27b_merge_final.yaml
# 或：
python merge_lora.py --base Qwen/Qwen3-27B --lora output/qwen_full_stage3 --output qwen_beibei_final

# 量化 GGUF（本地部署）
python convert_to_gguf.py qwen_beibei_final --outtype q4_k_m
```

合并输出：`./qwen_beibei_final`（或 `./output/qwen_merged_final`）  
GGUF：`./qwen_beibei_final/qwen_beibei_final-q4_k_m.gguf`
