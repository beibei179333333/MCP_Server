# Telegram All-in-One Bot

参考开源项目 **[tgcf](https://github.com/aahnik/tgcf)** 的插件化搬运架构 + 主流 Telegram 运营机器人的常见模块，融合并适配为一套**可商用**的一站式机器人系统：

| 模块 | 能力 |
|---|---|
| 📡 **搬运（tgcf 风格）** | 多源 → 多目标；插件链（filter / replace / format / caption / media / length / sender / watermark）；历史回填；断点续传 |
| 📒 **记账** | 自然语言录入；今日/月度报表；走势图；预算+超额告警；CSV 导出；定期入账（房租/订阅） |
| 📣 **群发** | 即时 / 定时 / 标签分群；内联按钮；进度展示；失败自动屏蔽；调度器自动触发 |
| 💬 **自动回复** | 包含 / 正则；按群隔离 + 全局；权重 + 冷却；内联按钮 |
| 👋 **群组管理** | 入群欢迎；按钮 / 算术验证码；超时自动踢出；反链接 / 反炸群 / 反转发 |
| 💎 **订阅 / 付费** | 4 档套餐；试用 → 续费；订单 → 截图 → 管理员确认 → 自动开通；订阅过期自动到期 |
| 🪪 **引荐 / 标签** | 用户标签、积分、引荐码（已建模） |
| 🖥 **Web 控制台** | FastAPI + Jinja2；仪表盘 / 用户 / 规则 / 群发 / 订阅；Session 鉴权；健康检查端点 |
| ⏰ **调度器** | APScheduler；定时群发 / 订阅到期 / 定期入账 / 验证码超时 |

---

## 🚀 部署（≥ 30 秒）

### 方式 1 — Docker（推荐）

```bash
git clone <repo> && cd MCP_Server
cp .env.example .env && nano .env       # 填 BOT_TOKEN / TG_API_* / ADMIN_IDS
docker compose run --rm bot python run.py   # 首次：交互式登录 user-bot（Ctrl+C 退出）
docker compose up -d --build                # 正式后台运行
docker compose logs -f bot
```

镜像构建会经过：
1. `python:3.11-slim` 基础层
2. apt 安装 `build-essential / libffi / libjpeg` 等
3. `pip install -r requirements.txt`（30+ 个包，含 Telethon、SQLAlchemy、APScheduler、FastAPI、Pillow、matplotlib、cryptg）

首次构建 **2-5 分钟**，二次依赖缓存 **< 30 秒**。

### 方式 2 — 一键安装脚本

```bash
sudo bash deploy/install.sh
sudo nano /opt/telegram-bot/.env
cd /opt/telegram-bot && sudo .venv/bin/python run.py   # user-bot 首次登录
sudo systemctl start telegram-bot
```

### 方式 3 — 本机调试

```bash
make install     # 创建 venv + 装依赖 + 生成 .env
make run         # 启动
make test        # 跑测试
```

---

## 🔧 必备凭据

1. **BOT_TOKEN** — [@BotFather](https://t.me/BotFather) 创建
2. **TG_API_ID / TG_API_HASH** — <https://my.telegram.org/apps>
3. **TG_PHONE** — user-bot 账号手机号（带国际区号）
4. **ADMIN_IDS** — 你自己的 Telegram User ID（多个用逗号分隔）

填入 `.env` 后启动。Web 后台默认 `http://<server>:8000`，用户名 `admin`，密码留空时由 `WEB_SECRET` 哈希派生（启动日志会提示）。

---

## 📦 命令速查

```text
🔹 通用
/start /menu /help /id /cancel

🔹 记账（私聊）
120 餐饮 午餐         直接输入即可记账
+5000 工资 / -50 打车
/ledger /today /month /chart /export
/budget 餐饮 1500     设置月预算
/budgets              查看预算执行

🔹 自动回复
/ar_add 关键词 ::: 回复
/ar_add_re ^正则$ ::: 回复
/ar_list /ar_toggle <id> /ar_del <id>

🔹 订阅
/plans /mysub
/grant_sub <user_id> <plan_code>   # 管理员手动开通
/payments

🔹 群组（群管理员）
/welcome 文本   /welcome_off
/captcha                          # 切换入群验证
/antispam                         # 切换反垃圾

🔹 搬运（管理员）
/fw_add 源 目标[,目标2] [名字]
/fw_filter <id> kw=A,B bl=C,D
/fw_replace <id> 原文 => 新文
/fw_caption <id> header=🔥 | footer=—@CH
/fw_format <id> links=1 mentions=1 emoji=0 collapse=1
/fw_media <id> allow=photo,video,text
/fw_watermark <id> @MyChannel
/fw_backfill <id> 200              # 历史回填
/fw_plugins <id>                   # 查看完整 JSON
/fw_list /fw_toggle /fw_del /fw_reload

🔹 群发（管理员）
/broadcast users 内容
/broadcast chats     （回复一条消息）
/broadcast tag VIP 内容
内容可附加 @schedule 2030-01-01 10:00      → 定时
内容可附加 @buttons [["按钮","https://..."]] → 内联按钮
```

---

## 🧩 项目结构

```
MCP_Server/
├── run.py                              启动入口
├── requirements.txt
├── .env.example
├── Dockerfile / docker-compose.yml / .dockerignore
├── Makefile
├── pytest.ini
├── deploy/
│   ├── install.sh                      Ubuntu/Debian 一键安装
│   └── telegram-bot.service            systemd 单元
├── tests/                              pytest 套件
└── bot/
    ├── config.py / logger.py / utils.py / keyboards.py
    ├── database.py                     SQLAlchemy async 模型（13 张表）
    ├── userbot.py                      Telethon 搬运执行器（多目标 + 回填）
    ├── scheduler.py                    APScheduler（4 个定时任务）
    ├── plugins/                        tgcf 风格插件链
    │   ├── base.py                     PluginChain / MessageContext
    │   ├── filters.py                  filter / media / length / sender
    │   ├── transforms.py               replace / format / caption
    │   └── watermark.py                Pillow 图片水印
    ├── handlers/                       Telegram 命令 / 回调
    │   ├── common.py /admin.py /router.py
    │   ├── ledger.py                   记账 + 预算
    │   ├── autoreply.py                自动回复
    │   ├── broadcast.py                即时 / 定时 / 标签 / 内联按钮
    │   ├── forward_admin.py            插件 CRUD
    │   ├── group.py                    欢迎 / 验证码 / 反垃圾
    │   └── subscription.py             套餐 / 订阅 / 付费
    └── web/                            FastAPI 控制台
        ├── app.py
        └── templates/                  Jinja2 模板（6 个页面）
```

---

## 🔐 安全 & 数据

- `.env` / `*.session` / `data/` 已加入 `.gitignore`
- 群发失败的用户自动 `is_blocked`，下次不再尝试
- FloodWait 自动 sleep 重试
- Web 后台使用 Session + `secrets.compare_digest` 防时序攻击
- 默认 SQLite；改 `DATABASE_URL` 即可切 PostgreSQL：
  ```
  DATABASE_URL=postgresql+asyncpg://bot:bot@postgres/botdb
  ```
- systemd 单元已加 `NoNewPrivileges` / `ProtectSystem` 安全约束

---

## 🧪 验证

- `make test` — 12 个用例（解析器 / 插件链 / 数据库约束）全部通过
- FastAPI `/healthz` 健康检查；Docker `HEALTHCHECK` 自动监控
- 51 个 Telegram handler 装配通过

---

## 📜 致谢

本项目搬运核心架构受 [tgcf](https://github.com/aahnik/tgcf)（MIT）启发，并融合：
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [Telethon](https://github.com/LonamiWebs/Telethon)
- [FastAPI](https://github.com/tiangolo/fastapi) + [APScheduler](https://github.com/agronholm/apscheduler)

MIT License.
