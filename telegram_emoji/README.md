# 批量修改 Telegram 表情包名称 (telegram_emoji)

把一批 **自定义表情包（custom emoji set）** 的显示名称统一改成：

```
更多表情 @emojipd
```

涉及的表情包就是 `sets.txt` 里列的那些（`https://t.me/addemoji/<名字>` 里
`addemoji/` 后面的那一段），共 39 个，例如
`beibei56_by_pindaobianjiqibot` …… `beibei96_by_pindaobianjiqibot`
（其中没有 65、80）。

---

## ⚠️ 必须用「机器人本人」的 Token

Telegram 的 `setStickerSetTitle` 接口**只能改“本机器人自己创建”的表情包**。
这些包的名字都以 `_by_pindaobianjiqibot` 结尾，说明它们是
**@pindaobianjiqibot** 这个机器人创建的，所以**必须用这个机器人的
Bot Token** 才能改名。用别的机器人 Token 会报
`STICKERSET_INVALID` / “sticker set not found”。

> Token 形如 `123456789:AAH...`，从 @BotFather 里 `/mybots → 选机器人 → API Token`
> 可以拿到（前提是这个机器人是你的）。

---

## 用法

先**空跑**预览（不联网、不改动，确认列表和名称没问题）：

```bash
python telegram_emoji/rename_emoji_titles.py --dry-run
```

确认无误后，提供 Token 真正执行（三选一）：

```bash
# 方式 A：环境变量（推荐）
export TELEGRAM_BOT_TOKEN="123456789:AAH..."
python telegram_emoji/rename_emoji_titles.py

# 方式 B：命令行参数
python telegram_emoji/rename_emoji_titles.py --token "123456789:AAH..."

# 方式 C：放到 token.txt（已被 .gitignore 忽略，不会提交）
echo "123456789:AAH..." > telegram_emoji/token.txt
python telegram_emoji/rename_emoji_titles.py
```

跑完会打印每个包的 `OK / FAIL`，结尾给出成功数量和失败清单。

---

## 常用参数

| 参数 | 作用 | 默认 |
|------|------|------|
| `--dry-run` | 只预览不执行，不联网 | 关 |
| `--title "文本"` | 自定义要改成的名称（1–64 字符） | `更多表情 @emojipd` |
| `--names-file 路径` | 换一份表情包名单 | `telegram_emoji/sets.txt` |
| `--token 值` | 直接传 Token | 读环境变量 / token.txt |
| `--sleep 秒` | 每个包之间的间隔（防限流） | 0.5 |

接口遇到 `429` 限流会按 `retry_after` 自动等待重试；网络错误会指数退避重试。

---

## 改名单

直接编辑 `sets.txt`：每行一个表情包名字，`#` 开头或行尾 `# 备注` 都会被忽略。
