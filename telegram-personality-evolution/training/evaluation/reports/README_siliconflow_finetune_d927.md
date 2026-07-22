# 硅基流动（SiliconFlow）微调路径

本机是 **Apple M4 Pro / 24GB**，跑不动 Qwen3-27B / 72B 本地训练。  
改用硅基流动云端微调；训完后在本机用 API 调用。

## 账号

- AK 管理：https://cloud.siliconflow.cn/me/account/ak
- 微调控制台：https://cloud.siliconflow.cn/fine-tune
- Key 放在项目根目录 `.env`（已 gitignore），**不要把 Key 贴到聊天里**

## 可选微调模型（平台当前支持）

| 模型 | 说明 |
|------|------|
| **Qwen/Qwen2.5-72B-Instruct** | 可微调里最强（推荐） |
| Qwen/Qwen2.5-32B-Instruct | 更强性价比 |
| Qwen/Qwen2.5-14B-Instruct | 中等 |
| Qwen/Qwen2.5-7B-Instruct | 最便宜 / 最快 |

> 注意：平台微调 LoRA Rank **上限 64**（不是本地 Axolotl 的 128）。  
> 推理广场里虽有 Qwen3.6-27B 等，但**微调列表目前仍是 Qwen2.5 系列**。

## 一键准备数据

```bash
python3 prepare_siliconflow_finetune.py \
  --max-samples 20000 \
  --include-knowledge
```

产物：`train_data_siliconflow/{train,val}_messages.jsonl`

## API 已上传的文件（2026-07-22）

| 角色 | file id | 本地文件 |
|------|---------|----------|
| 训练集 | `file-xrz10w7h9oxwtnj` | `train_messages.jsonl`（20000 条） |
| 验证集 | `file-1h5mg6le15jiks9` | `val_messages.jsonl`（1000 条） |

控制台开训：https://cloud.siliconflow.cn/fine-tune  
基座：**Qwen/Qwen2.5-72B-Instruct**  
建议：LR `0.0001` / Epochs `2` / Batch `8` / MaxTokens `4096` / LoRA Rank `64` / Alpha `64`

> 硅基流动**没有**公开的「创建微调任务」API，只能网页点开始。  
> 重新上传：`python3 upload_siliconflow_finetune.py`  
> 训完调用：`python3 chat_siliconflow.py --model <微调模型ID>`


## 本机调用

```bash
# 冒烟（基座）
python3 chat_siliconflow.py --model Qwen/Qwen2.5-72B-Instruct --prompt "在吗"

# 微调完成后（换成控制台给的模型 ID）
python3 chat_siliconflow.py --model <ft-model-id> --prompt "对方询价能量怎么回"
```

## 和本地 Axolotl 方案的关系

| 方案 | 状态 |
|------|------|
| 本地 Axolotl Qwen3-27B | 本机无 CUDA，阻塞 |
| 硅基流动 Qwen2.5-72B 微调 | **当前可走通的主路径** |
