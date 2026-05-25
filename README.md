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

## 📱 手机网页版（推荐）

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

| 参数 | 作用 |
|------|------|
| （默认）| 去掉无用户名、广告/营销号、bot、scam/fake |
| `--keep-no-username` | 保留没有用户名的号 |
| `--keep-ads` | 保留广告/营销号 |
| `--keep-bots` | 保留 bot |
| `--keep-scam` | 保留 scam/fake |
| `--ad-threshold N` | 广告判定阈值，越小越严格（默认 2） |
| `--ad-keywords-file FILE` | 自定义广告关键词表（每行一个，`#` 开头为注释） |
| `--dump-removed` | 额外导出 `xxx.removed.csv`，列出被过滤掉的成员及原因 |

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
