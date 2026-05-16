# Telegram 多功能机器人

一个**生产级**的多功能 Telegram 机器人，覆盖运营 / 副业常见场景：

| 模块 | 能力 |
| --- | --- |
| 📡 **自动搬运** | 监听任意公开/私有频道、群组的消息，按关键词过滤、文本替换后实时转发到你的目标群（基于 Telethon user-bot） |
| 📒 **记账助手** | 私聊一句 `120 餐饮 午餐` 即可入账，今日/月度报表、近 30 天走势图、CSV 导出 |
| 📣 **群发中心** | 一键发往所有订阅用户 / 关联群组 / 全部，自动节流、失败标记、断点续推 |
| 💬 **自动回复** | 关键词包含 / 正则匹配，全局或单群作用域，命中计数 |
| 📊 **管理面板** | 用户列表、群组列表、规则统计、群发历史 |

## 🚀 快速开始

### 1. 准备账号

1. 在 [@BotFather](https://t.me/BotFather) 创建一个 bot，记下 `BOT_TOKEN`。
2. 访问 <https://my.telegram.org/apps> 申请 `api_id` / `api_hash`（搬运功能必须）。
3. 准备一个**普通用户账号**用于搬运（无需 Premium），手机号需带国际区号，例如 `+8613800000000`。
4. 通过 [@userinfobot](https://t.me/userinfobot) 查询你的 `User ID`，加入 `ADMIN_IDS`。

### 2. 安装与配置

```bash
git clone <repo>
cd MCP_Server

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# 编辑 .env 填入 BOT_TOKEN / TG_API_ID / TG_API_HASH / TG_PHONE / ADMIN_IDS
```

### 3. 首次运行（user-bot 登录）

```bash
python run.py
```

首次启动会提示输入手机短信验证码（如果开启二步验证还会要求密码）。完成后会生成 `userbot.session`，下次启动自动复用。

### 4. 把 bot 加进你的群组 / 频道

- 将 bot 拉进群（或设为频道管理员），即可在 `/admin → 群组列表` 看到。
- 群发与自动回复需要 bot 在群中。

---

## 📦 命令速查

通用：
```
/start /menu       打开主菜单
/help              帮助
/id                查看当前会话/用户 ID
/cancel            取消当前操作
```

记账（私聊）：
```
120 餐饮 午餐       直接发送即可入账（支出）
+5000 工资          收入
-50 打车            支出
/ledger             面板
/today /month       今日 / 本月汇总
/chart              近 30 天走势图
/export             导出 CSV
```

自动回复（群中由群管理员配置）：
```
/ar_add 关键词 ::: 回复内容
/ar_add_re ^你好.*$ ::: 自动回复
/ar_list
/ar_toggle <id>
/ar_del <id>
```

搬运规则（仅 bot 管理员）：
```
/fw_add @source @target 规则名
/fw_filter <id> keywords=优惠,打折 | blacklist=广告
/fw_replace <id> 原文 => 新文
/fw_toggle <id>
/fw_del <id>
/fw_list
/fw_reload        让 user-bot 立即重读规则
```

群发（仅 bot 管理员）：
```
/broadcast               进入面板
/broadcast users 你好    向所有用户发文本
/broadcast chats         (回复一条消息后执行) 把消息转发到所有群
/broadcast both          全部目标
```

管理：
```
/admin /stats /users /chats
```

---

## 🗂 项目结构

```
MCP_Server/
├── run.py                  # 启动入口
├── requirements.txt
├── .env.example
└── bot/
    ├── config.py           # 配置加载
    ├── logger.py           # 日志
    ├── database.py         # SQLAlchemy 模型 / 异步 session
    ├── keyboards.py        # 内联键盘
    ├── utils.py            # 工具函数、装饰器
    ├── userbot.py          # Telethon 搬运执行
    ├── main.py             # Application 装配
    └── handlers/
        ├── common.py       # /start /help /menu
        ├── ledger.py       # 记账
        ├── autoreply.py    # 自动回复
        ├── broadcast.py    # 群发
        ├── forward_admin.py# 搬运规则 CRUD
        ├── admin.py        # 管理员面板 / chat 追踪
        └── router.py       # 文本消息路由
```

## 🔐 数据安全

- 所有数据落地到 SQLite（`bot.db`），异步访问，可随时切换到 PostgreSQL（改 `DATABASE_URL`）。
- `userbot.session` / `.env` 已在 `.gitignore` 中，**绝不要**提交到仓库。
- 群发失败的用户会被自动标记为 `is_blocked`，下次群发自动跳过。
- 频率控制：`BROADCAST_INTERVAL_MS` 默认 80ms / 条，命中 FloodWait 会自动等待重试。

## 🧩 扩展建议

- 多账户记账：在 `ledger.py` 中已为 `LedgerAccount` 预留 `owner_id+name` 唯一约束，可直接加 `/account_new` 命令。
- 付费订阅：在 `User` 表加 `paid_until` 字段，群发前做过滤即可形成 **会员制群发服务**。
- Webhook 部署：把 `start_polling` 换成 `start_webhook` 即可。

## 📝 许可

MIT。
