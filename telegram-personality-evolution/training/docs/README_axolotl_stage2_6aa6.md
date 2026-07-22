# Axolotl Stage2（商务续训）

## 命令

```bash
cd "/Users/home/Downloads/压缩包/skills/telegram-personality-evolution"

axolotl train config/qwen3.6_27b_business_stage2.yaml \
  --resume_from_checkpoint ./output/qwen_personality_stage1
```

## 前置条件（缺一不可）

1. 已安装 Axolotl（CUDA≥12.4 / NVIDIA GPU）
2. Stage1 已训练完成，且 `./output/qwen_personality_stage1` 内有真实权重  
   （至少含 LoRA adapter 或 `checkpoint-*` / `trainer_state.json`）
3. 商务子集数据：
   - `train_data_business_stage2/train.jsonl`
   - `train_data_business_stage2/val.jsonl`

## 本机状态

- Apple Silicon：无 CUDA，**不能**本地执行该命令
- 当前 `output/qwen_personality_stage1/`：**空目录**（尚无 Stage1 权重可 resume）

请先在 GPU 机器跑完 Stage1，再执行上述 Stage2 续训。
