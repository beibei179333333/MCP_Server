# Telegram SMM 自动增长引擎 (`smm_growth`)

按一份 YAML 配置（频道列表、SMM 面板 API、主力/辅助服务、30 天渐进增长曲线），
自动计算**每天每个频道该下哪些单**，并通过标准 SMM 面板 API v2 下单。

- **主力服务**：粉丝（每天，按增长曲线）、浏览量、反应（AUTO，每 7 天续单）。
- **辅助服务**：评论、分享（每天，需帖子链接）、多地区粉丝、Premium 粉丝（每 7 天）。
- **渐进增长**：数量随天数从 `start` 平滑爬升到 `end`，叠加确定性抖动（可复现）。
- **安全**：API key 不写进仓库，从环境变量读取；`dry_run` 默认开启，先演练再真跑。
- **稳健**：下单失败按 `max_retries` 指数退避重试；主服务失败自动切备用服务。

> ⚠️ 这是一套营销自动化工具，用于增长**你自己**的频道。请遵守 Telegram 及各
> SMM 面板的服务条款，自行承担相关费用与风险。

---

## 1. 安装

```bash
pip install -r requirements.txt        # 需要 requests + pyyaml
```

## 2. 配置 API key（不要提交到 git）

`smm_growth/campaign.yaml` 里的 key 用环境变量占位符，运行前先设置：

```bash
export SMMFOLLOWS_API_KEY="你的 smmfollows key"
export SMMSTONE_API_KEY="你的 smmstone key"
export FENBA_API_KEY="你的 fenba key"      # 当前配置未用到，可留空
```

> `dry_run=true`（默认）时不需要 key 也能演练计划与花费。
> 想用别的配置文件：所有命令都支持 `--config 路径.yaml`；本地私有副本建议命名
> `*.local.yaml`（已在 `.gitignore` 中忽略）。

## 3. 先看计划（不下单）

```bash
# 整套 30 天汇总：各类单数、总数量、预计花费
python -m smm_growth plan --summary

# 某一天 / 第 N 天具体要下哪些单
python -m smm_growth plan --date 2026-06-02
python -m smm_growth plan --day 0

# 把整套周期逐单导出为 CSV（便于核对/存档）
python -m smm_growth plan --day 0 --all --csv schedule.csv
```

## 4. 演练 → 真正下单

```bash
# 演练今天的下单（默认就是 dry-run，不花钱）
python -m smm_growth run --date 2026-06-02

# 确认无误后，真正下单（覆盖配置里的 dry_run）
python -m smm_growth run --date 2026-06-02 --execute

# 只跑某些类别 / 某个频道
python -m smm_growth run --date 2026-06-02 --only members,views --channel Hpaydq
```

### 评论 / 分享需要帖子链接

评论、分享是针对**具体帖子**的，不是整个频道。运行时用 `--posts` 提供
「频道链接 → 帖子链接」映射（每行一对，空格或逗号分隔）：

```text
# posts.txt
https://t.me/Hpaydq      https://t.me/Hpaydq/1234
https://t.me/Wanbiaoge   https://t.me/Wanbiaoge/567
```

```bash
python -m smm_growth run --date 2026-06-02 --execute --posts posts.txt
```

未提供某频道帖子链接时，该频道的评论/分享会被**跳过并告警**（其它单照常）。

## 5. 余额 / 订单状态

```bash
python -m smm_growth balance
python -m smm_growth status --panel smmfollows --order 12345 --order 12346
```

---

## 配置说明（`campaign.yaml`）

| 段落 | 作用 |
|------|------|
| `start_date` / `duration_days` / `posts_per_day` | 活动起始、周期、每天发帖数 |
| `channels` | 频道列表（`name` + `link`） |
| `panels` | 各 SMM 面板的 `url` 与 `key`（key 用 `${ENV}` 占位） |
| `growth` | 各增长曲线：`start`/`end`/`curve`/`jitter_pct`（可省，回退默认） |
| `services.members` | 粉丝服务（每天下单，数量由 `growth.members` 决定） |
| `services.views` / `services.reactions` | AUTO 服务（每 7 天续单，数量=每帖目标值） |
| `addon_services.comment` / `share` | 评论/分享（每天 `daily_qty`，需帖子链接） |
| `addon_services.regional_members` | 多地区粉丝（每 7 天，每地区 `qty_per_region_per_week`） |
| `addon_services.premium_members` | Premium 粉丝（每 7 天 `qty_per_week`） |
| `execution` | `dry_run`、下单/频道间隔、重试次数与退避 |

每个服务都可有 `primary` + `backup`：主服务下单失败会自动切到备用。
数量会被裁剪到该服务的 `min_order`/`max_order`（例如某地区 `min_order=100` 时，
配置的 35 会被抬到 100）。

### 增长曲线形状

- `linear`：匀速增长
- `ease_in`：慢启动、后期加速（默认用于粉丝，避免一开始增长过猛）
- `ease_out`：快启动、后期放缓
- `s_curve`：两头慢、中间快

`jitter_pct` 给每天数量一个 ±比例 的确定性浮动（同一频道同一天结果固定，可复现核对）。

---

## 每天自动执行

配合系统计划任务即可每天自动跑（先把 `SMM*_API_KEY` 写进环境）：

```bash
# crontab 示例：每天 10:00 执行当天计划（评论/分享用当天的 posts.txt）
0 10 * * *  cd /path/to/MCP_Server && python -m smm_growth run --execute --posts posts.txt >> smm.log 2>&1
```

## 测试（离线，无需网络/key）

```bash
python tests/test_smm.py
# 或 python -m pytest tests/test_smm.py -q
```
