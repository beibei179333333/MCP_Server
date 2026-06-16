# G789 场景技能 · Telegram 机器人 (`g789_bot`)

把全部 **500 个 G789 场景技能**（S-001 … S-500）部署成一个可直接运行的 Telegram 聊天机器人。
用户在 Telegram 里**按类目浏览 / 关键词搜索 / 输入场景编号**选定一个场景，然后像聊天一样对话，
机器人会以该场景的自包含工作流（内嵌 System Prompt）为人格，由 **Claude** 实时生成回复。

- 场景数据：`g789_bot/skills/`（5 个安装包，共 500 个 `SKILL.md`，单文件自包含）
- 模型后端：官方 `anthropic` SDK，默认 `claude-opus-4-8`，流式输出，按场景做 Prompt 缓存
- 机器人框架：`python-telegram-bot`（异步，v21+），长轮询，无需公网入站端口

---

## 1. 准备两个密钥

1. **Telegram Bot Token**：在 Telegram 里找 [@BotFather](https://t.me/BotFather) → `/newbot` → 拿到形如
   `123456789:AA...` 的 token。
2. **Anthropic API Key**：在 [platform.claude.com](https://platform.claude.com) 创建，形如 `sk-ant-...`。

> ⚠️ 两个密钥都是机密，**不要提交进 git**。仓库的 `.gitignore` 已忽略 `.env` / `*.token`。

## 2. 安装并运行（本地 / 服务器）

```bash
pip install -r requirements.txt          # 安装依赖（含 python-telegram-bot, anthropic）

export TELEGRAM_BOT_TOKEN="123456789:AA..."
export ANTHROPIC_API_KEY="sk-ant-..."
python -m g789_bot                        # 启动，开始长轮询
```

也可以把密钥写进项目根目录的 `.env`（参考 `.env.example`），直接 `python -m g789_bot` 会自动读取。

启动后在 Telegram 里给你的机器人发 `/start` 即可。

### 离线自检（不需要任何密钥 / 网络）

```bash
python -m g789_bot --selftest            # 校验 500 个技能能正确加载、分类、搜索
python -m g789_bot --list 20             # 打印前 20 个场景
python tests/test_bot_skills.py          # 跑单元测试
```

## 3. 机器人用法

| 操作 | 说明 |
|------|------|
| `/start` `/menu` | 主菜单（按类目浏览 / 随机 / 帮助） |
| 直接发关键词或编号 | 搜索场景，例如 `购物`、`PPT`、`S-042` |
| `/search <关键词>` | 同上 |
| `/skill S-100` | 直接进入指定场景 |
| `/random` | 随机一个场景 |
| `/current` | 查看当前场景 |
| `/end` | 退出当前场景，回到搜索/浏览 |

选定场景后，直接发消息就会以该场景助手的身份回复（流式输出）。每个会话独立保存最近若干轮上下文。

## 4. 配置项（环境变量）

| 变量 | 默认 | 作用 |
|------|------|------|
| `TELEGRAM_BOT_TOKEN` | —（必填） | Telegram 机器人 token |
| `ANTHROPIC_API_KEY` | —（必填） | Anthropic API Key |
| `ANTHROPIC_MODEL` | `claude-opus-4-8` | 使用的模型（如需更省成本可设 `claude-sonnet-4-6`） |
| `G789_EFFORT` | `medium` | 思考/投入档位：`low`/`medium`/`high`/`max` |
| `G789_MAX_HISTORY_TURNS` | `16` | 每个会话保留的最近消息条数 |
| `G789_MAX_OUTPUT_TOKENS` | `4000` | 单次回复最大 token |
| `G789_BLOCKED_CATEGORIES` | 空 | 隐藏整类场景，逗号分隔，例如 `黄,赌` |
| `G789_ADMIN_IDS` | 空 | 预留：管理员 Telegram 数字 ID，逗号分隔 |

> **内容说明**：场景库里包含 `黄`（成人，30 个）、`赌`（博彩，30 个）等类目。这些技能本身是
> 「流程脚手架」（如本地化、合规审查、戒断辅导等），不含露骨内容，运行时也受模型自身安全策略约束。
> 如运营方希望对外服务时不提供这些类目，设 `G789_BLOCKED_CATEGORIES=黄,赌` 即可一键隐藏。

## 5. 部署到云端（Render，零服务器）

仓库已带 `render.yaml`，其中新增了一个 **worker** 服务 `g789-telegram-bot`：

1. Render → New + → **Blueprint** → 选择本仓库 → Apply。
2. 在 `g789-telegram-bot` 服务的 **Environment** 里填入 `TELEGRAM_BOT_TOKEN` 和 `ANTHROPIC_API_KEY`
   （`render.yaml` 里已标记 `sync: false`，需要在面板手动填）。
3. 部署完成后机器人即自动长轮询运行，无需公网端口。

也可用任意支持 `Procfile` 的平台：仓库 `Procfile` 已加 `bot: python -m g789_bot`。

## 6. 工作原理

```
Telegram 用户 ──▶ python-telegram-bot（异步handlers）
                     │  浏览/搜索 → 选定场景(S-XXX)
                     ▼
            g789_bot/skills.py  解析 500 个 SKILL.md → Catalog（id/类目/搜索索引）
                     │  选定场景的整篇 SKILL.md = System Prompt
                     ▼
            g789_bot/llm.py  AsyncAnthropic.messages.stream(
                                system=[wrapper, 场景正文(缓存)],
                                messages=该会话历史)
                     ▼
            流式文本 ──▶ 编辑同一条 Telegram 消息逐步显示
```

- Messages API 是无状态的，因此每轮把该会话的历史完整回传；超长会话自动裁剪到最近 N 条。
- 场景正文较大，作为带 `cache_control` 的 System Prompt 块缓存，同一会话后续轮次只付约 0.1× 的缓存读取价。
