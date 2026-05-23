# MCP_Server

批量克隆 Telegram 表情包并统一重命名。

把 `packs.txt` 里 97 个 `t.me/addemoji/...` / `t.me/addstickers/...` 链接全部克隆,统一改成:

- **title**: `会员表情🔥 @emojipd`
- **short_name**: `emojipd_001` ~ `emojipd_097`

提供两套方案,**推荐方案 A**(用你自己的 bot,全自动、无 flood 限速):

| | 方案 A:Bot API 直接克隆 | 方案 B:Telethon 走 @fStikBot |
| --- | --- | --- |
| 脚本 | `clone_via_bot.py` | `clone_packs.py` |
| 用什么 | 你的 bot token(@Biaoqing111bot) | 你的 Telegram 账号(api_id/hash) |
| 新链接后缀 | `_by_Biaoqing111bot` | `_by_fStikBot` |
| 限速风险 | 低 | 较高 |
| 进度文件 | `state_bot.json` | `state.json` |

> 注意:bot **不能**和 @fStikBot 对话,所以用 bot token 时新包必然归你的 bot 所有,链接后缀变成 `_by_Biaoqing111bot`,例如 `t.me/addemoji/emojipd_001_by_Biaoqing111bot`。

---

## 方案 A:Bot API 直接克隆(推荐)

原理:用 bot token 调 `getStickerSet` 读源包 → 复制贴纸 → `createNewStickerSet` 建新包。完全不经过 @fStikBot。

### 1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env,至少填 TG_BOT_TOKEN
```

关键变量:

| 变量 | 说明 |
| --- | --- |
| `TG_BOT_TOKEN` | @Biaoqing111bot 的 token |
| `BOT_OWNER_ID` | 新包归属的用户数字 ID。**留空**则自动取“最近给 bot 发过消息的人”。 |
| `NEW_TITLE` | 统一标题,默认 `会员表情🔥 @emojipd` |
| `SHORT_PREFIX` | short_name 前缀,默认 `emojipd` |
| `REUSE_FILE_ID` | `1`=复用源 file_id(快);失败自动回退到下载再上传 |
| `TEST_LIMIT` | 只处理前 N 个包做测试,`0`=全部 |

> **重要**:新包必须有一个“归属用户”。请先用你的 Telegram 账号给 **@Biaoqing111bot** 发任意一条消息(比如 `/start`),脚本就能自动识别你为归属者;或者在 `.env` 里手动填 `BOT_OWNER_ID`(可向 @userinfobot 查自己的数字 ID)。

### 3. 先小规模测试

```bash
# .env 里设 TEST_LIMIT=2,先跑 2 个确认没问题
python clone_via_bot.py
```

确认生成的两个新包能正常打开后,把 `TEST_LIMIT` 改回 `0`,删掉 `state_bot.json`,再跑完整 97 个:

```bash
rm -f state_bot.json
python clone_via_bot.py
```

### 4. 结果

新链接写在 `state_bot.json`,每条形如:

```json
{
  "index": 1,
  "source_url": "https://t.me/addemoji/tie105_by_fStikBot",
  "source_name": "tie105_by_fStikBot",
  "new_name": "emojipd_001_by_Biaoqing111bot",
  "new_url": "https://t.me/addemoji/emojipd_001_by_Biaoqing111bot",
  "sticker_count": 50,
  "status": "done",
  "error": null
}
```

中途断了或部分失败,直接重跑 `python clone_via_bot.py` 会跳过已完成的、只补未完成的。

---

## 方案 B:Telethon 走 @fStikBot(备选)

如果你一定要让新链接后缀保持 `_by_fStikBot`,只能用自己的 Telegram 账号去和 @fStikBot 对话。

1. 到 <https://my.telegram.org/apps> 申请 `api_id` / `api_hash`,填进 `.env`。
2. `pip install -r requirements.txt`
3. `python clone_packs.py`,首次跑输短信验证码登录。

脚本会对每个包依次:`/cancel → /cloneemojipack → 原链接 → 新 short_name → 新 title`,抓回新链接写入 `state.json`。每步之间有延时(`STEP_DELAY` / `PACK_DELAY`)以降低限速概率。

---

## 注意事项

- **short_name 全网唯一**:`emojipd_001` 之类若已被占用,该条会标记为 `failed`,改 `SHORT_PREFIX` 或手动改进度文件后重跑。
- **限速**:遇到 429 方案 A 会按 `retry_after` 自动等待重试;方案 B 捕获 `FloodWaitError` 后自动等待。
- **第 14 个链接是 `addstickers`**(普通贴纸,非 emoji),脚本会自动按源包的 `sticker_type` 处理,生成 `t.me/addstickers/...` 链接。
