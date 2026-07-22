# Axolotl Stage1（当前配置）

## 配置文件

`config/qwen3.6_27b_personality_stage1.yaml`

- base_model: `Qwen/Qwen3-27B`
- 4bit + LoRA（r=64, alpha=16）
- sequence_len: 8192
- epochs: 2
- output: `./output/qwen_personality_stage1`

## 数据

| 文件 | 条数 |
|------|------|
| `train_data_final/train.jsonl` | 71433 |
| `train_data_final/val.jsonl` | 3771 |

格式：Alpaca（`instruction` / `input` / `output`）

## 训练命令（CUDA 机器）

```bash
cd "/Users/home/Downloads/压缩包/skills/telegram-personality-evolution"
axolotl train config/qwen3.6_27b_personality_stage1.yaml
```

本机 Apple Silicon 无 CUDA，不能直接训练。
