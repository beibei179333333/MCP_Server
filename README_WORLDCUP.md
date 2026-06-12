# ⚽️ 2026 世界杯实时通知 Telegram 机器人

一个**完整可运行**的 Telegram 机器人：自动追踪 2026 世界杯赛事，**开赛提醒、进球、半场、终场比分**第一时间推送给所有订阅者。支持中文 / English 双语、按用户开关各类通知、小组积分榜查询。

> 只依赖一个第三方库 `requests`，其余全部用 Python 标准库实现，开箱即跑。
> **没有 API Key 也能立刻体验** —— 内置「演示模式」会用一场加速进行的模拟比赛，
> 在约 2 分钟内把开球→进球→半场→进球→终场的整条通知链路完整演示一遍。

---

## ✨ 功能一览

| 能力 | 说明 |
|------|------|
| 🔔 实时通知 | 开赛提醒、开球、每个进球、半场、终场结果，自动推送给所有订阅者 |
| 🌐 双语 | 每个用户可用 `/lang` 在 **中文 / English** 间切换，独立记忆 |
| ⚙️ 个性化 | `/settings` 内联按钮，逐项开关「提醒/开球/进球/半场/终场」 |
| 🗓️ 查询命令 | `/today` 今日赛程、`/live` 进行中、`/next` 接下来、`/matches` 全部、`/standings` 积分榜 |
| 🕒 时区显示 | 通过 `TIMEZONE` 设置，比如 `Asia/Shanghai` |
| 💾 持久化 | 订阅者与赛事状态存 SQLite，重启不丢、不会重复推送 |
| 📣 群发 | 管理员可用 `/broadcast` 发公告 |
| 🧪 离线自测 | `selftest` 子命令无需网络即可验证通知逻辑 |

---

## 🚀 三步跑起来

### 1) 创建你的机器人，拿到 Token
在 Telegram 里找 **@BotFather** → 发送 `/newbot` → 按提示取名 → 得到形如
`123456789:AAH...xyz` 的 **Token**。

### 2) 配置
```bash
cp .env.example .env
# 编辑 .env，至少填入：
#   TELEGRAM_BOT_TOKEN=你的Token
# （可选）填 FOOTBALL_DATA_API_KEY 用真实赛事数据，不填则自动演示模式
```

### 3) 启动
```bash
# 方式 A：一键脚本（自动装依赖）
./run_bot.sh

# 方式 B：手动
pip install -r worldcup_bot/requirements.txt
python -m worldcup_bot run
```

启动后，去 Telegram 给你的机器人发 **`/start`** 即可订阅。完成 ✅

---

## 📡 用真实赛事数据（football-data.org，免费）

演示模式用的是模拟数据。要推真实的世界杯赛果：

1. 到 https://www.football-data.org/client/register 免费注册，拿到 API Key。
2. 在 `.env` 里填 `FOOTBALL_DATA_API_KEY=你的Key`（`PROVIDER` 保持 `football-data`）。
3. 重启机器人即可。

> 免费版限速 10 次/分钟，默认 `POLL_INTERVAL_SECONDS=60`（每分钟 1 次）已经很稳。
> 世界杯赛事代码为 `WC`（`COMPETITION=WC`）。

---

## 💬 机器人命令

| 命令 | 作用 |
|------|------|
| `/start` | 订阅并查看帮助 |
| `/today` | 今日赛程 |
| `/live` | 正在进行的比赛（含实时比分/分钟） |
| `/next` | 接下来 5 场 |
| `/matches` | 全部赛程（近 24h 内已结束 + 进行中 + 未来） |
| `/standings` | 小组积分榜 |
| `/settings` | 开关各类通知（内联按钮） |
| `/lang` | 中文 / English |
| `/subscribe` `/unsubscribe` | 订阅 / 取消订阅 |
| `/whoami` | 查看本会话 chat id |
| `/broadcast <消息>` | 管理员群发（需配置 `ADMIN_CHAT_ID`） |

把机器人**拉进群**并给它发命令，整个群也能收到通知（群里需 `/start` 一次）。

---

## 🧪 验证与自测

```bash
# 离线自测：验证开球/进球/半场/终场的检测逻辑（无需网络、无需 Token）
python -m worldcup_bot selftest

# 检查配置与数据源连通性（会打印抓到的前几场比赛）
python -m worldcup_bot check

# 完整单元测试
python -m pytest tests/test_worldcup.py -q
```

---

## 🐳 用 Docker 部署

```bash
docker build -t worldcup-bot .
docker run -d --name worldcup-bot \
  -e TELEGRAM_BOT_TOKEN=你的Token \
  -e FOOTBALL_DATA_API_KEY=你的Key \
  -e TIMEZONE=Asia/Shanghai \
  -v "$(pwd)/data:/app/data" \
  --restart unless-stopped \
  worldcup-bot
```

后台长期运行（裸机）也可以用 `nohup python -m worldcup_bot run &`，或写成 systemd 服务。

---

## ⚙️ 配置项（环境变量 / `.env`）

| 变量 | 默认 | 说明 |
|------|------|------|
| `TELEGRAM_BOT_TOKEN` | — | **必填**，BotFather 的 Token |
| `FOOTBALL_DATA_API_KEY` | — | football-data.org Key；不填则演示模式 |
| `PROVIDER` | `football-data` | `football-data` 或 `demo` |
| `COMPETITION` | `WC` | 赛事代码（世界杯 `WC`） |
| `POLL_INTERVAL_SECONDS` | `60` | 轮询间隔（演示模式自动用 12s） |
| `REMINDER_MINUTES` | `15` | 开赛前多少分钟提醒 |
| `TIMEZONE` | `UTC` | 显示时区，如 `Asia/Shanghai` |
| `DEFAULT_LANG` | `zh` | 默认语言 `zh`/`en` |
| `DB_PATH` | `worldcup_bot.db` | SQLite 路径 |
| `ADMIN_CHAT_ID` | — | 管理员会话 id，启用 `/broadcast` |

---

## 🏗️ 架构

```
worldcup_bot/
├── __main__.py        入口：run / check / selftest 子命令
├── config.py          读取环境变量 / .env（自带轻量解析，无额外依赖）
├── telegram.py        Telegram Bot API 客户端（requests + 长轮询）
├── models.py          统一的 Match 数据模型 + football-data 归一化
├── providers/
│   ├── football_data.py  真实数据源（带缓存、限速友好）
│   └── demo.py           演示数据源（含加速进行的模拟直播）
├── storage.py         SQLite：订阅者 / 设置 / 赛事状态（线程安全）
├── notifier.py        事件检测（开球/进球/半场/终场）+ 分发
├── formatting.py      消息排版（国旗 emoji、时区、HTML）
├── flags.py           国家→国旗 emoji
├── i18n.py            中英文案
├── bot.py             命令处理 + 主循环（命令线程 + 轮询线程）
└── selftest.py        离线自测
```

**工作原理**：一个线程长轮询 `getUpdates` 处理用户命令；另一个线程每隔
`POLL_INTERVAL_SECONDS` 拉取一次赛事数据，与数据库里「上次状态」对比，
检测出状态/比分变化后生成事件，按每个订阅者的语言与开关推送。首次拉取只
建立基线、不推送，避免启动时刷屏；订阅者拉黑机器人会被自动清理。

---

## ❓ 常见问题

- **启动报「未设置 TELEGRAM_BOT_TOKEN」**：把 BotFather 的 Token 填进 `.env`。
- **收不到通知**：先 `/start` 订阅；`/settings` 看对应开关是否为 ✅；演示模式下
  一场模拟比赛约 2 分钟跑完一轮，开球后稍等即可看到进球/半场/终场。
- **真实数据没有比赛**：确认 `FOOTBALL_DATA_API_KEY` 正确、`COMPETITION=WC`，
  并用 `python -m worldcup_bot check` 看抓取结果。
- **连不上 Telegram**：确认运行环境能访问 `api.telegram.org`（部分网络需代理）。
