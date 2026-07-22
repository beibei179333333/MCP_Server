# 🎓 Telegram 人格演化 - 模型训练指南
# Model Training Guide / Hướng dẫn Huấn luyện Mô hình

版本 / Version: v1.0  
更新 / Updated: 2026-07-22

---

## 📖 目录 / Table of Contents

1. [训练概述](#训练概述)
2. [三阶段训练流程](#三阶段训练流程)
3. [配置文件说明](#配置文件说明)
4. [训练环境](#训练环境)
5. [快速开始](#快速开始)
6. [详细步骤](#详细步骤)
7. [模型合并与量化](#模型合并与量化)
8. [本地训练方案](#本地训练方案)
9. [云端微调](#云端微调)
10. [故障排除](#故障排除)

---

## 🎯 训练概述 / Training Overview

### 训练目标 / Training Goals

基于Telegram私聊数据,训练个性化语言模型:

- 🧠 **Stage 1 (人格)**: 学习核心人格特征、语气、表达风格
- 💼 **Stage 2 (商务)**: 强化商务沟通、专业表达
- 📚 **Stage 3 (全量+知识)**: 巩固全量数据,注入知识上下文

### 模型架构 / Model Architecture

**基础模型 / Base Model:**
- Qwen/Qwen3-27B (主训练)
- Qwen/Qwen3-8B (MLX本地训练)

**LoRA配置 / LoRA Configuration:**
- `lora_r: 128` (强化长期记忆容量)
- `lora_alpha: 64`
- 目标模块: q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj

**注意事项 / Important Notes:**
⚠️ `r=128`配置**不可**与旧`r=64` checkpoint混用,须从Stage1重训

---

## 🔄 三阶段训练流程 / Three-Stage Training Pipeline

```
Stage 1: 人格基础 (Personality Foundation)
   ↓
   → 学习核心人格特征、语气、情感表达
   → 训练数据: 高质量人格数据集
   → Epochs: 3-5
   ↓
Stage 2: 商务强化 (Business Enhancement)
   ↓
   → 从Stage1 checkpoint继续训练
   → 强化商务沟通、专业表达、行业知识
   → 训练数据: 商务专项数据集
   → Epochs: 2-3
   ↓
Stage 3: 全量巩固 (Full Consolidation)
   ↓
   → 从Stage2 checkpoint继续训练
   → 全量数据巩固 + 知识上下文注入
   → 训练数据: 完整数据集 + knowledge context
   → Epochs: 2-3
   ↓
Final Model: 合并 & 量化 (Merge & Quantize)
```

---

## 📋 配置文件说明 / Configuration Files

### NVIDIA CUDA 训练 (Axolotl)

| 文件 | 用途 | 阶段 |
|------|------|------|
| `qwen3.6_27b_personality_stage1.yaml` | Stage1人格训练配置 | 1 |
| `qwen3.6_27b_business_stage2.yaml` | Stage2商务训练配置 | 2 |
| `qwen3.6_27b_full_stage3.yaml` | Stage3全量训练配置 | 3 |
| `qwen3.6_27b_merge_final.yaml` | 最终合并配置 | 合并 |

### Apple Silicon 本地训练 (MLX)

| 文件 | 用途 | 说明 |
|------|------|------|
| `mlx_qwen3_8b_lora.yaml` | MLX本地训练配置 | 适用于Mac M系列芯片 |

### 自动化脚本

| 文件 | 用途 |
|------|------|
| `run_train_and_merge.sh` | 一键完整训练+合并脚本 |

---

## 🖥️ 训练环境 / Training Environment

### 方案一: NVIDIA CUDA (推荐高性能训练)

**硬件要求:**
- GPU: NVIDIA A100/H100 (40GB+ VRAM)
- RAM: 64GB+
- Storage: 500GB+ SSD

**软件要求:**
```bash
# CUDA 11.8+
# PyTorch 2.0+
# Axolotl框架

# 安装Axolotl
pip install axolotl
# 或从源码安装
git clone https://github.com/OpenAccess-AI-Collective/axolotl
cd axolotl
pip install -e .
```

### 方案二: Apple Silicon (MLX本地训练)

**硬件要求:**
- Mac M1/M2/M3 系列
- 统一内存: 32GB+ (推荐64GB)

**软件要求:**
```bash
# MLX框架
pip install mlx mlx-lm

# 或使用官方脚本
git clone https://github.com/ml-explore/mlx-examples
cd mlx-examples/lora
```

### 方案三: SiliconFlow 云端微调

**优势:**
- 无需本地GPU
- 按需付费
- 快速部署

**准备:**
- SiliconFlow API密钥
- 准备好的训练数据集

---

## 🚀 快速开始 / Quick Start

### 方法一: 一键自动训练 (推荐)

```bash
cd telegram-personality-evolution/training

# 确保已准备好训练数据
# train_data_final/train.jsonl
# train_data_final/val.jsonl
# train_data_business_stage2/train.jsonl
# train_data_business_stage2/val.jsonl
# train_data_knowledge/context.jsonl

# 执行自动训练脚本
bash scripts/run_train_and_merge.sh
```

**脚本会自动执行:**
1. Stage1 人格训练
2. Stage2 商务训练
3. Stage3 全量训练
4. LoRA合并
5. GGUF量化

**预计时间:** 6-12小时 (取决于硬件)

### 方法二: 手动分步训练

```bash
cd telegram-personality-evolution/training

# Stage 1: 人格基础
axolotl train configs/qwen3.6_27b_personality_stage1.yaml

# Stage 2: 商务强化
axolotl train configs/qwen3.6_27b_business_stage2.yaml \
  --resume_from_checkpoint ./output/qwen_personality_stage1

# Stage 3: 全量巩固
axolotl train configs/qwen3.6_27b_full_stage3.yaml \
  --resume_from_checkpoint ./output/qwen_business_stage2

# 合并LoRA
python ../../scripts/merge_lora_*.py \
  --base Qwen/Qwen3-27B \
  --lora output/qwen_full_stage3 \
  --output qwen_beibei_final

# 量化GGUF
python ../../scripts/convert_to_gguf_*.py \
  qwen_beibei_final --outtype q4_k_m
```

---

## 📚 详细步骤 / Detailed Steps

### Step 1: 准备训练数据

```bash
cd ../../scripts

# 生成训练数据集
python3 prepare_training_data_*.py \
  --add-knowledge \
  --output ../training/data

# 验证数据格式
python3 -c "
import json
from pathlib import Path

for split in ['train', 'val']:
    file = Path(f'../training/data/train_data_final/{split}.jsonl')
    if file.exists():
        lines = file.read_text().strip().split('\n')
        sample = json.loads(lines[0])
        print(f'{split}: {len(lines)} samples')
        print(f'Sample keys: {list(sample.keys())}')
"
```

**数据集结构:**
```json
{
  "instruction": "用户问题或场景",
  "input": "",
  "output": "模型回复",
  "system": "系统提示词 (可选)"
}
```

### Step 2: 配置检查

```bash
# 检查配置文件
cat configs/qwen3.6_27b_personality_stage1.yaml | grep -E "lora_r|lora_alpha|base_model|datasets"

# 预期输出:
# base_model: Qwen/Qwen3-27B
# lora_r: 128
# lora_alpha: 64
# datasets: ...
```

### Step 3: Stage 1 训练 (人格基础)

```bash
# 开始训练
axolotl train configs/qwen3.6_27b_personality_stage1.yaml

# 监控训练
# 查看日志: tail -f output/qwen_personality_stage1/logs/training.log
# 查看TensorBoard: tensorboard --logdir output/qwen_personality_stage1/tensorboard
```

**训练参数:**
- Learning rate: 2e-4
- Batch size: 4 (per device)
- Gradient accumulation: 4
- Epochs: 3-5
- Warmup ratio: 0.1

**预期输出:**
```
output/qwen_personality_stage1/
├── adapter_config.json
├── adapter_model.bin
├── checkpoint-*/
└── logs/
```

### Step 4: Stage 2 训练 (商务强化)

```bash
# 从Stage1 checkpoint继续训练
axolotl train configs/qwen3.6_27b_business_stage2.yaml \
  --resume_from_checkpoint ./output/qwen_personality_stage1

# 监控训练进度
watch -n 10 'tail -20 output/qwen_business_stage2/logs/training.log'
```

**训练参数调整:**
- Learning rate: 1e-4 (降低,避免遗忘)
- Epochs: 2-3
- 数据集: 商务专项数据

### Step 5: Stage 3 训练 (全量巩固)

```bash
# 从Stage2 checkpoint继续训练
axolotl train configs/qwen3.6_27b_full_stage3.yaml \
  --resume_from_checkpoint ./output/qwen_business_stage2

# 包含knowledge context
# train_data_knowledge/context.jsonl
```

**训练参数:**
- Learning rate: 5e-5 (进一步降低)
- Epochs: 2-3
- 数据集: 全量数据 + 知识上下文

---

## 🔧 模型合并与量化 / Model Merge & Quantization

### 合并LoRA权重

**方法一: 使用Axolotl**

```bash
axolotl merge-lora configs/qwen3.6_27b_merge_final.yaml
```

输出: `./output/qwen_merged_final`

**方法二: 使用自定义脚本**

```bash
python ../../scripts/merge_lora_*.py \
  --base Qwen/Qwen3-27B \
  --lora output/qwen_full_stage3 \
  --output qwen_beibei_final \
  --precision float16
```

输出: `./qwen_beibei_final`

**验证合并:**
```bash
# 检查模型文件
ls -lh qwen_beibei_final/

# 预期文件:
# - config.json
# - generation_config.json
# - model-*.safetensors
# - tokenizer.json
# - tokenizer_config.json
```

### 量化为GGUF格式

**适用于本地CPU/Metal推理:**

```bash
# Q4_K_M量化 (推荐,性能平衡)
python ../../scripts/convert_to_gguf_*.py \
  qwen_beibei_final \
  --outtype q4_k_m \
  --outfile qwen_beibei_final-q4_k_m.gguf

# 其他量化选项:
# --outtype q8_0  # 更高质量,更大体积
# --outtype q5_k_m  # 中等质量
# --outtype q4_0  # 更小体积
```

**GGUF模型使用:**
```bash
# 使用llama.cpp推理
./llama.cpp/main \
  -m qwen_beibei_final-q4_k_m.gguf \
  -p "你好，请介绍一下自己" \
  -n 256

# 使用Ollama
ollama create qwen_beibei -f qwen_beibei_final-q4_k_m.gguf
ollama run qwen_beibei
```

---

## 💻 本地训练方案 (Apple Silicon) / Local Training on Apple Silicon

### 使用MLX框架

**适用于:** Mac M1/M2/M3系列,32GB+统一内存

**配置文件:** `configs/mlx_qwen3_8b_lora.yaml`

```bash
# 安装MLX
pip install mlx mlx-lm

# 准备数据 (转换为MLX格式)
python -c "
import json
from pathlib import Path

# 读取Alpaca格式数据
data = []
with open('../data/train_data_final/train.jsonl') as f:
    for line in f:
        data.append(json.loads(line))

# 转换为MLX格式
mlx_data = []
for item in data:
    mlx_data.append({
        'text': f\"### Instruction:\\n{item['instruction']}\\n\\n### Response:\\n{item['output']}\"
    })

# 保存
with open('../data/mlx_train.jsonl', 'w') as f:
    for item in mlx_data:
        f.write(json.dumps(item, ensure_ascii=False) + '\\n')
"

# 开始训练
mlx_lm.lora \
  --model Qwen/Qwen3-8B \
  --train \
  --data ../data/mlx_train.jsonl \
  --config configs/mlx_qwen3_8b_lora.yaml \
  --iters 1000
```

**MLX训练优势:**
- ✅ 无需NVIDIA GPU
- ✅ 统一内存架构,高效
- ✅ 功耗低
- ⚠️ 模型规模受限 (8B max推荐)

**详细文档:** 查看`docs/README_mlx_local_train_*.md`

---

## ☁️ 云端微调 (SiliconFlow) / Cloud Fine-tuning

### 准备数据

```bash
# 使用SiliconFlow格式准备数据
python ../../scripts/prepare_siliconflow_finetune_*.py \
  --input ../data/train_data_final \
  --output ../data/siliconflow_format

# 上传数据集
python ../../scripts/upload_siliconflow_finetune_*.py \
  --dataset ../data/siliconflow_format \
  --api-key YOUR_API_KEY
```

### 启动微调任务

```bash
# 通过API启动
curl -X POST https://api.siliconflow.cn/v1/fine-tuning/jobs \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-27B",
    "training_file": "file-xxx",
    "validation_file": "file-yyy",
    "hyperparameters": {
      "n_epochs": 3,
      "learning_rate": 2e-4,
      "batch_size": 4
    }
  }'
```

### 监控与下载

```bash
# 查询任务状态
curl https://api.siliconflow.cn/v1/fine-tuning/jobs/ftjob-xxx \
  -H "Authorization: Bearer YOUR_API_KEY"

# 下载微调后的模型
# (完成后会提供下载链接)
```

**详细文档:** 查看`docs/README_siliconflow_finetune_*.md`

---

## 🔍 监控与评估 / Monitoring & Evaluation

### 训练监控

```bash
# TensorBoard
tensorboard --logdir output/

# 实时日志
tail -f output/qwen_*/logs/training.log

# GPU监控
watch -n 1 nvidia-smi
```

### 评估指标

| 指标 | 说明 | 目标值 |
|------|------|--------|
| Training Loss | 训练损失 | < 0.5 |
| Validation Loss | 验证损失 | < 0.6 |
| Perplexity | 困惑度 | < 10 |
| Learning Rate | 学习率 | 动态调整 |

### 质量评估

```bash
# 生成测试对话
python ../../scripts/chat_siliconflow_*.py \
  --model ./qwen_beibei_final \
  --test-prompts test_prompts.txt

# 评估脚本
python ../../scripts/eval_rule_vs_qwen_deep_*.py \
  --model ./qwen_beibei_final \
  --test-set ../data/test_set.jsonl
```

---

## ⚠️ 故障排除 / Troubleshooting

### 常见问题

**1. CUDA Out of Memory**

```bash
# 解决方案:
# - 减小batch_size
# - 增加gradient_accumulation_steps
# - 使用更小的模型
# - 启用gradient_checkpointing

# 修改配置:
batch_size: 2  # 从4降到2
gradient_accumulation_steps: 8  # 从4增到8
gradient_checkpointing: true
```

**2. 训练loss不下降**

```bash
# 检查:
# - 学习率是否过大/过小
# - 数据质量
# - 模型是否正确加载checkpoint

# 调整学习率:
learning_rate: 1e-4  # 尝试降低
warmup_steps: 100  # 增加warmup
```

**3. 验证loss上升 (过拟合)**

```bash
# 解决方案:
# - 减少epochs
# - 增加dropout
# - 使用更多验证数据
# - 启用early stopping

# 配置:
num_epochs: 2  # 从3降到2
dropout: 0.1
early_stopping_patience: 3
```

**4. LoRA合并失败**

```bash
# 检查:
# - lora_r和lora_alpha是否匹配
# - checkpoint路径是否正确
# - 基础模型版本是否一致

# 重新下载基础模型:
huggingface-cli download Qwen/Qwen3-27B --local-dir ./models/qwen3-27b
```

**5. MLX训练速度慢**

```bash
# 优化:
# - 减小batch_size
# - 使用较小的模型 (8B → 4B)
# - 减少数据集大小
# - 关闭不必要的后台程序
```

---

## 📊 训练时间估算 / Training Time Estimates

### NVIDIA A100 (40GB)

| 阶段 | 数据量 | 预计时间 |
|------|--------|----------|
| Stage 1 | ~10K samples | 2-3 hours |
| Stage 2 | ~5K samples | 1-2 hours |
| Stage 3 | ~15K samples | 3-4 hours |
| 合并 & 量化 | - | 30-60 min |
| **总计** | - | **6-10 hours** |

### Apple M2 Max (64GB)

| 阶段 | 模型 | 预计时间 |
|------|------|----------|
| Full Training | Qwen3-8B | 8-12 hours |
| 合并 & 量化 | - | 20-40 min |

### SiliconFlow云端

| 任务 | 预计时间 |
|------|----------|
| 数据上传 | 5-10 min |
| 微调训练 | 2-4 hours |
| 模型下载 | 10-20 min |

---

## 📁 输出文件结构 / Output File Structure

```
training/
├── output/
│   ├── qwen_personality_stage1/
│   │   ├── adapter_config.json
│   │   ├── adapter_model.bin
│   │   └── checkpoint-*/
│   ├── qwen_business_stage2/
│   │   └── ...
│   ├── qwen_full_stage3/
│   │   └── ...
│   └── qwen_merged_final/
│       └── ...
├── qwen_beibei_final/              # 最终合并模型
│   ├── config.json
│   ├── generation_config.json
│   ├── model-*.safetensors
│   ├── tokenizer.json
│   └── tokenizer_config.json
└── qwen_beibei_final-q4_k_m.gguf   # GGUF量化模型
```

---

## 🎓 进阶技巧 / Advanced Tips

### 1. 混合精度训练

```yaml
# 配置文件
fp16: true
bf16: false  # A100支持bf16,更稳定
```

### 2. 梯度裁剪

```yaml
max_grad_norm: 1.0  # 防止梯度爆炸
```

### 3. 学习率调度

```yaml
lr_scheduler: cosine
warmup_ratio: 0.1
```

### 4. 数据增强

```bash
# 回译增强
python augment_data.py \
  --input train.jsonl \
  --method backtranslation \
  --output train_augmented.jsonl
```

### 5. 多GPU训练

```bash
# DeepSpeed ZeRO-2
accelerate launch \
  --config_file deepspeed_config.yaml \
  train.py
```

---

## 📚 参考文档 / Reference Documents

### 详细分步指南

- 📖 `docs/README_axolotl_stage1_*.md` - Stage1详细步骤
- 📖 `docs/README_axolotl_stage2_*.md` - Stage2详细步骤
- 📖 `docs/README_axolotl_stage3_*.md` - Stage3详细步骤
- 📖 `docs/README_axolotl_pipeline_*.md` - 完整流程概述

### 专项文档

- 📖 `docs/README_mlx_local_train_*.md` - Apple Silicon本地训练
- 📖 `docs/README_merge_gguf_*.md` - 模型合并与GGUF转换
- 📖 `docs/README_siliconflow_finetune_*.md` - SiliconFlow云端微调

### 配置文件

- ⚙️ `configs/qwen3.6_27b_personality_stage1.yaml`
- ⚙️ `configs/qwen3.6_27b_business_stage2.yaml`
- ⚙️ `configs/qwen3.6_27b_full_stage3.yaml`
- ⚙️ `configs/qwen3.6_27b_merge_final.yaml`
- ⚙️ `configs/mlx_qwen3_8b_lora.yaml`

---

## 🎯 最佳实践 / Best Practices

### 训练建议

1. ✅ **数据质量第一** - 宁少勿滥,确保高质量训练数据
2. ✅ **渐进式训练** - 严格按照Stage1→2→3顺序,不要跳步
3. ✅ **保存checkpoint** - 每个阶段都保存完整checkpoint
4. ✅ **监控过拟合** - 密切关注validation loss
5. ✅ **小规模测试** - 先用小数据集测试完整流程

### 资源管理

1. 💾 **磁盘空间** - 预留至少500GB空间
2. 🔋 **GPU利用率** - 保持80%+利用率
3. 💰 **成本控制** - 云端训练注意费用
4. ⏰ **时间规划** - 预留充足训练时间

### 版本管理

1. 📝 **记录训练参数** - 详细记录每次训练配置
2. 🏷️ **标记checkpoint** - 清晰标记stage和版本
3. 📊 **保存评估结果** - 记录loss和评估指标
4. 🔄 **备份模型** - 关键checkpoint及时备份

---

## 🎊 完成检查清单 / Completion Checklist

### 训练前

- [ ] 训练数据已准备 (train.jsonl, val.jsonl)
- [ ] 配置文件已检查
- [ ] 环境已安装 (Axolotl/MLX)
- [ ] 磁盘空间充足 (500GB+)
- [ ] GPU/内存充足

### 训练中

- [ ] Stage1训练完成,checkpoint已保存
- [ ] Stage2训练完成,checkpoint已保存
- [ ] Stage3训练完成,checkpoint已保存
- [ ] Loss曲线正常,无异常波动
- [ ] 验证loss < 0.6

### 训练后

- [ ] LoRA已成功合并
- [ ] GGUF模型已量化
- [ ] 模型已测试,输出正常
- [ ] 文件已备份
- [ ] 文档已更新

---

## 📞 支持与反馈 / Support & Feedback

遇到问题请查阅:
1. 本文档"故障排除"章节
2. 详细分步文档 (`docs/README_*.md`)
3. 项目主README
4. 提交Issue

---

**训练指南版本**: v1.0  
**最后更新**: 2026-07-22  
**状态**: ✅ 完整可用

---

🎉 **祝训练顺利！Good luck with training!**
