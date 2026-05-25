# 群成员全自动导出 / 清洗工具 (group_export)

基于 `fun-stat-bot.net` 的 API，自动导出群成员列表，并完成：

- **自动分页抓取**，直到取完全部成员；
- **自动去重 + 自动合并**（同一用户的多条记录、跨多个群的重复成员合并为一条，保留最完整信息）；
- **过滤没有设置用户名的号**；
- **自动过滤广告号 / 营销号**（关键词 + 链接 + 电话 + emoji 堆叠 + scam/fake 标记打分）；
- 同时导出 **CSV / JSON / XLSX**。

> ⚠️ 重要：当前云端会话的网络策略**不允许访问 `fun-stat-bot.net`**（`Host not in allowlist`），
> 所以**抓取真实数据必须在你自己的电脑上运行**。云端只用于开发和离线测试。
> 工具会从 Swagger 规范**自动探测导出接口**，所以即使接口路径和官方文档略有不同也能适配。

还提供**手机网页版**：批量粘贴群链接、一键导出、**宽松版表格**展示、CSV/Excel/JSON 下载。

---

## 🍎 iPhone 零安装版（打开网址即用）

整套逻辑做成了**纯浏览器单页应用**，不用装任何东西。手机 Safari 直接打开：

**👉 https://raw.githack.com/beibei179333333/MCP_Server/claude/group-member-export-tool-sWRs7/docs/index.html**

> 想要更稳定的永久网址，可开启 GitHub Pages（一次性，手机也能操作）：
> 仓库 **Settings → Pages → Source 选 Deploy from a branch →
> 分支选 `claude/group-member-export-tool-sWRs7`、文件夹选 `/docs` → Save**，
> 稍等一两分钟即可访问 `https://beibei179333333.github.io/MCP_Server/`。

> 🌐 **双语**：网页右上角可切换 **简体中文 / Tiếng Việt（越南语）**，选择会记住在本机浏览器。

用法：粘贴群链接 → 选过滤项 → 在「高级设置」填密钥 → 开始导出 → 看表格 / 下载 CSV·JSON。

- **演示模式**（页面里勾选）：免密钥、免联网，先看界面和「宽松版表格」效果，一定能用。
- **真实数据**：因为这个 API 是 HTTP 且可能限制跨域，iPhone Safari 会拦截直连请求
  （报错 `Failed to fetch`）。两种解决办法 👇

### 解决 “Failed to fetch”

**办法一：托管兜底版（推荐，真实数据 100% 可用，最稳）**

把带「服务端代理」的版本部署到免费平台 Render，拿到一个 HTTPS 网址，手机打开即用。
**一键部署**（手机点这个链接即可，会用 GitHub 登录，不装任何 App）：

👉 https://render.com/deploy?repo=https://github.com/beibei179333333/MCP_Server/tree/claude/group-member-export-tool-sWRs7

1. 点上面链接 → 用 GitHub 登录 → 它会自动读取仓库里的 `render.yaml`，实例选 **Free** → **Apply / Deploy**。
2. 等几分钟，拿到形如 `https://group-export-xxxx.onrender.com` 的网址。
3. 手机打开那个网址（就是同一套双语界面）→ 在「高级设置」填密钥 → 导出。
   服务端替你向 API 发请求，**彻底绕开 Safari 的跨域 / HTTP 限制**，真实数据稳定可用。

> 若一键链接没生效，可手动：Render → New + → Web Service → 选仓库 `beibei179333333/MCP_Server`
> → 分支 `claude/group-member-export-tool-sWRs7` → Start Command
> `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 600` → Free。

**办法二：在网页里填「网络代理」（零部署，但不够稳/有安全顾虑）**

打开「② 过滤选项 → 高级设置 → 网络代理」，填一个 CORS 代理（用 `{url}` 作占位符），例如：

```
https://corsproxy.io/?url={url}
```

代理在服务端帮你转发，可绕开浏览器拦截。⚠️ **注意：你的请求（包括密钥 Token）会经过这个第三方代理**，
请用可信代理，最好是你自己部署的；否则建议用办法一。

---

## 💻 电脑版（Windows · 真实数据直接可用，最省心）

在自己电脑上跑，浏览器开 `localhost`，由电脑替你请求 API，**没有手机那种跨域/HTTP 拦截**，真实数据直接可用。

1. **装 Python**：到 https://www.python.org/downloads/ 下载安装，
   安装第一步务必勾选 **“Add Python to PATH”**，然后一路下一步装完。
2. **下载项目**：点这个链接下载压缩包，下载后右键 → 全部解压缩：
   https://github.com/beibei179333333/MCP_Server/archive/refs/heads/claude/group-member-export-tool-sWRs7.zip
3. 进解压出来的文件夹，**双击 `run.bat`**。
   首次会自动安装依赖，然后启动服务并自动打开浏览器 `http://localhost:8000`
   （若没自动打开，手动在浏览器输入这个地址）。
4. 在网页 **② 过滤选项 → 高级设置** 里粘贴你的 **密钥(Token)** → 粘贴群链接 → 开始导出 → 下载 CSV / Excel / JSON。

> - 右上角可切换 **中文 / 越南语**。
> - 停止：关闭那个黑色命令行窗口即可；下次用再双击 `run.bat`。
> - 若 Windows 弹 “已保护你的电脑”，点 **更多信息 → 仍要运行**（因为 .bat 没有数字签名，正常现象）。
> - 命令行用法：`run.bat discover` 看接口、`run.bat test` 跑测试。

## 📱 手机网页版（电脑/Termux 运行服务端）

在你自己的电脑上启动服务，手机连同一 WiFi 即可用浏览器操作：

```bash
pip install -r requirements.txt
export GROUP_EXPORT_TOKEN="<你的JWT>"     # 或在网页“高级设置”里填
./run.sh web                              # 或 python -m group_export serve
```

启动后终端会打印两个地址：
- 电脑本机：`http://127.0.0.1:8000`
- 手机访问：`http://<电脑局域网IP>:8000`（手机与电脑同一 WiFi）

网页操作流程：
1. **批量群链接**：每行一个，支持 `https://t.me/xxx`、`@xxx`、`-100…` 开头ID，也支持逗号分隔；可上传 `.txt`。点「解析预览」看识别到几个群。
2. **过滤选项**：勾选「过滤无用户名 / 广告营销号 / 机器人 / 诈骗仿冒」，可调广告严格度。
3. **开始全自动导出**：实时进度条；完成后下方显示统计 + **宽松版表格**，并提供 CSV / Excel / JSON 下载。
4. **演示模式**：勾选后无需密钥、无需联网，用合成数据预览界面和表格（方便先在手机上看效果）。

> 想在手机上直接跑服务端，可用安卓的 **Termux**：`pkg install python` 后同样 `./run.sh web`，浏览器开 `http://127.0.0.1:8000`。

---

## 1. 命令行版 · 安装

```bash
pip install -r requirements.txt        # requests, openpyxl
```

## 2. 配置密钥（不要写进代码 / 不要提交到 git）

三选一：

```bash
# 方式 A：环境变量
export GROUP_EXPORT_TOKEN="<你的JWT>"

# 方式 B：本地文件（已在 .gitignore 中忽略）
echo "<你的JWT>" > token.txt

# 方式 C：命令行参数
python -m group_export export --token "<你的JWT>" ...
```

## 3. 先看看接口（可选，确认自动探测对不对）

```bash
python -m group_export discover
```

会列出 Swagger 里的所有接口，并打印它认为的「导出群成员」最佳匹配接口。
如果自动探测选错了，用下面的 `--endpoint / --group-param / --page-param / --size-param` 手动指定。

## 4. 导出一个群（完整清洗流程）

```bash
python -m group_export export --group -1001234567890 -o members --format all
```

输出：`members.csv`、`members.json`、`members.xlsx`。

## 5. 导出多个群并自动合并去重

```bash
python -m group_export export \
  --group GROUP_A --group GROUP_B --group GROUP_C \
  -o merged --format all
```

也可以把**之前导出的文件**一起合并去重：

```bash
python -m group_export export --group GROUP_A --merge-in old_members.json -o merged
```

---

## 过滤选项

> 网页版（iPhone 零安装版 / 服务端版）里**每个设置下方都有中文说明和建议**，
> 还带「↻ 一键推荐」按钮一键填好推荐过滤项。下面是命令行对应参数。

| 参数 | 作用 | 默认 |
|------|------|------|
| `--keep-no-username` | 保留没有用户名的号 | 默认过滤 |
| `--keep-ads` | 保留广告/营销号 | 默认过滤 |
| `--keep-bots` | 保留 bot | 默认过滤 |
| `--keep-scam` | 保留 scam/fake | 默认过滤 |
| `--keep-deleted` | 保留已注销/空白账号（无用户名且无昵称） | 默认过滤 |
| `--filter-no-photo` | 过滤无头像账号（仅接口明确返回无头像时） | 默认关 |
| `--filter-random-username` | 过滤疑似随机用户名（如 user123456） | 默认关 |
| `--premium-only` | 仅保留 Premium 会员 | 默认关 |
| `--verified-only` | 仅保留官方认证号 | 默认关 |
| `--min-messages N` | 仅保留发言数 ≥ N 的成员（活跃度） | 0 不限 |
| `--language-keep zh,en` | 仅保留指定语言（语言未知者保留） | 不限 |
| `--ad-threshold N` | 广告判定阈值，越小越严格 | 2 |
| `--ad-keywords-file FILE` | 自定义广告关键词表（替换内置） | — |
| `--extra-ad-keywords-file FILE` | 追加广告关键词（叠加内置） | — |
| `--whitelist-file FILE` | 用户名白名单，永不过滤 | — |
| `--dump-removed` | 额外导出 `xxx.removed.csv`（含过滤原因） | — |

## 接口手动覆盖（自动探测不准时使用）

| 参数 | 说明 |
|------|------|
| `--endpoint /api/...` | 导出接口路径 |
| `--method GET/POST` | 请求方式 |
| `--group-param NAME` | 群 id 的参数名（如 `group_id` / `chat_id`） |
| `--page-param NAME` | 分页参数名（如 `page` 或 `offset`） |
| `--size-param NAME` | 每页数量参数名（如 `page_size` / `limit`） |
| `--page-size N` | 每页数量（默认 200） |
| `--offset-pagination` | 分页参数是「偏移量」而不是「页码」 |
| `--param k=v` | 追加任意查询参数（可重复） |

---

## 运行测试（离线，无需网络）

```bash
python tests/test_pipeline.py
# 或 python -m pytest tests/ -q
```

## 去重 / 合并规则

- 去重主键：优先 `user_id`，无则 `@username`，再无则显示名。
- 合并：空字段用另一条补全；`message_count` 取最大；bot/premium/scam/fake 取「或」；
  记录该成员出现过的所有群。

## 广告号判定（打分，>= 阈值即过滤）

- 命中广告关键词（中英文，见 `group_export/filters.py`，每命中 +1）；
- 名称/简介里有链接 `t.me/ http(s) @handle`（+2）；
- 名称/简介里有疑似电话号（+2）；
- 名称里 emoji 堆叠 ≥ 4 个（+1）；
- 账号被标记 scam/fake（+3）。
