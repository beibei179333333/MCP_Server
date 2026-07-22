# 本机 MLX 直接训练（不走硅基流动微调）

## 为什么

- 硅基流动：账号侧不让微调 / 不可用
- 本机无 NVIDIA CUDA，Axolotl + Qwen3-27B 跑不了
- 改用 **MLX-LM + Apple GPU**，直接在 M4 Pro 上训练

## 当前任务

| 项 | 值 |
|---|---|
| 模型 | `mlx-community/Qwen3-8B-4bit` |
| 数据 | `train_data_mlx/`（12000 train / 800 valid） |
| LoRA | rank=64，16 layers |
| 输出 | `output/mlx_qwen3_8b_lora/` |
| 日志 | `output/mlx_logs/train_qwen3_8b.log` |
| 配置 | `config/mlx_qwen3_8b_lora.yaml` |

## 命令

```bash
source .venv/bin/activate
python -m mlx_lm lora --config config/mlx_qwen3_8b_lora.yaml
```

## 训完后试聊

```bash
python -m mlx_lm generate \
  --model mlx-community/Qwen3-8B-4bit \
  --adapter-path output/mlx_qwen3_8b_lora \
  --prompt "对方只回「在吗」，用短句回一句。"
```

## 说明

24GB 统一内存下，**Qwen3-8B-4bit** 是稳妥可训档；14B 峰值约 22GB，容易和系统抢内存导致失败。若要冲 14B，可另开配置再试。
