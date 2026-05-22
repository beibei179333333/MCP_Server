# MCP_Server

批量克隆 Telegram 表情包并统一重命名的脚本。

把 `packs.txt` 里 97 个 `t.me/addemoji/...` / `t.me/addstickers/...` 链接全部通过 [@fStikBot](https://t.me/fStikBot) 克隆,统一改成:

- **title**: `会员表情🔥 @emojipd`
- **short_name**: `emojipd_001` ~ `emojipd_097`

进度持久化到 `state.json`,中途断了重跑会自动从下一个未完成的包继续。

## 使用步骤

### 1. 申请 Telegram API 凭证

打开 <https://my.telegram.org/apps>,登录后创建一个 application,记下 `api_id` 和 `api_hash`。

### 2. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env,填入 TG_API_ID / TG_API_HASH / TG_PHONE
```

可调参数:

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `NEW_TITLE` | `会员表情🔥 @emojipd` | 统一改写的标题 |
| `SHORT_PREFIX` | `emojipd` | short_name 前缀,会拼接 `_NNN` |
| `START_INDEX` | `1` | 起始序号 |
| `STEP_DELAY` | `3` | 每条消息之间等待秒数 |
| `PACK_DELAY` | `8` | 每个包完成后休息秒数,防 flood |

### 4. 运行

```bash
python clone_packs.py
```

首次运行会要求短信验证码登录;之后会读取 `clone_session.session` 免登录。

脚本会:

1. 给 @fStikBot 发 `/cancel` 重置状态
2. 发 `/cloneemojipack`(或链接是 `addstickers` 时发 `/clonepack`)
3. 等 bot 提示后,发送原始链接
4. 等 bot 提示后,发送新的 short_name
5. 等 bot 提示后,发送新的 title
6. 抓取 bot 返回的新链接,写入 `state.json`

每个包之间会等 `PACK_DELAY` 秒,降低被 Telegram 限速的概率。

### 5. 查看结果

```bash
cat state.json
```

每条记录形如:

```json
{
  "index": 1,
  "source_url": "https://t.me/addemoji/tie105_by_fStikBot",
  "new_short_name": "emojipd_001",
  "new_title": "会员表情🔥 @emojipd",
  "new_url": "https://t.me/addemoji/emojipd_001_by_fStikBot",
  "status": "done",
  "error": null
}
```

## 注意事项

- **flood 限制**:Telegram 对短时间内大量 bot 交互会限速。脚本里 `STEP_DELAY=3` 和 `PACK_DELAY=8` 是较保守的默认值;遇到 `FloodWaitError` 会自动等待并把状态置为 `pending`,重跑即可继续。
- **建议先小范围测试**:第一次跑可以先把 `packs.txt` 里只留 1~2 行试一下,确认 bot 的对话流程没变,再跑完整的 97 个。
- **short_name 全网唯一**:如果 `emojipd_001` 之类已被别人占用,bot 会报错,该条会被标记为 `failed`,你可以改 `SHORT_PREFIX` 或手动改 `state.json` 里的对应条目后重跑。
- **bot 流程可能变**:fStikBot 的提示文案如果变了,可以查看 `state.json` 里 `error` 字段,或在脚本运行时看到的 `<bot>` 打印,据此调整 `clone_packs.py` 里 `clone_one` 的顺序。
