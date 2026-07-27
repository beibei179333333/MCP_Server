# 用 MCP Server 把 6 台服务器接入 Claude（Agent 调用 + 管理）

这份指南回答一个问题：**「我有 6 台服务器，怎么让 Claude 通过 Agent 连上它们、调用并管理？」**

答案是本仓库新增的 `mcp_server` 包：一个 **MCP（Model Context Protocol）Server**，作为 Claude 和你服务器之间的桥梁。

---

## 1. 原理：为什么要一个「中间层」

Claude 本身不会 SSH，也不该拿到你的密钥。正确的做法是让 Claude 作为 **MCP 客户端（Agent）**，去调用一个你自己掌控的 **MCP Server**，由这个 Server 持有服务器清单和密钥、真正去执行 SSH / HTTP。

```
  你 ── 自然语言指令（"重启所有 web 机器的 nginx"）
   │
   ▼
  Claude（Agent = MCP 客户端）
   │   MCP 协议（本地 stdio 或远程 HTTP）
   │   它只会调用有名字的「工具」，比如 servers_run_group / servers_service
   ▼
  本 MCP Server（mcp_server 包）── 桥梁，读取 servers.json
   │   SSH（paramiko 或系统 ssh） / HTTP 健康检查
   ├──► web-1     (10.0.0.11)
   ├──► web-2     (10.0.0.12)
   ├──► app-1     (10.0.0.21)
   ├──► app-2     (10.0.0.22)
   ├──► db-1      (10.0.0.31)
   └──► staging-1 (10.0.1.10)
```

**好处**：密钥只存在 MCP Server 那一侧；Claude 只能做你在工具里允许的操作；可以整组批量下发；还能开只读模式先安全试跑。

---

## 2. 提供的 7 个工具

| 工具 | 作用 | 是否改动服务器 |
|------|------|:---:|
| `servers_list` | 列出清单里的所有服务器（可按标签过滤） | 只读 |
| `servers_health` | 检查 SSH 端口可达性 +（可选）HTTP 健康 URL | 只读 |
| `servers_status` | 一次拉取 uptime / 负载 / CPU / 内存 / 磁盘 / top 进程 | 只读 |
| `servers_logs` | tail 日志文件，或 `journalctl -u <服务>` | 只读 |
| `servers_run` | 在**单台**服务器上执行任意命令 | 会改动 |
| `servers_run_group` | 对**一组**服务器（按标签 / `all`）并发执行同一命令 | 会改动 |
| `servers_service` | `systemctl start/stop/restart/status <服务>` | 会改动 |

**目标选择器（selector）** 三种写法通用：服务器名（`web-1`）、标签（`web` / `prod`）、或字面量 `all`；也支持逗号组合（`web,db-1`）。

---

## 3. 安装

```bash
cd MCP_Server
python -m venv .venv && source .venv/bin/activate     # 建议用虚拟环境
pip install -r requirements-mcp.txt                    # mcp + paramiko + httpx
```

> `paramiko` 让你能用**密码或密钥**登录，且自带、无需系统 ssh。若你只用密钥、且系统有 `ssh`，也可以不装 paramiko（把 `backend` 设成 `ssh`）。

---

## 4. 配置你的 6 台服务器

复制示例并按需修改（`servers.json` 已被 `.gitignore`，不会误提交密钥）：

```bash
cp servers.example.json servers.json
```

`servers.json` 结构：

```json
{
  "defaults": { "user": "root", "port": 22, "key_file": "~/.ssh/id_ed25519" },
  "servers": [
    { "name": "web-1", "host": "1.2.3.4", "tags": ["web","prod"], "health_url": "http://1.2.3.4/healthz" },
    { "name": "db-1",  "host": "1.2.3.9", "tags": ["db","prod"], "user": "ubuntu", "use_sudo": true }
  ]
}
```

字段说明：

- `name`（必填）：唯一名字，Claude 用它指定目标。
- `host`（必填）：IP 或域名。
- `tags`：分组标签，`servers_run_group` 按标签批量下发。
- `key_file` / `password`：认证方式，二选一。**密码强烈建议走环境变量**（见下），不要写进文件。
- `health_url`：可选，`servers_health` 会额外 GET 它判断 2xx/3xx。
- `use_sudo`：为 true 时，服务控制等命令自动加 `sudo -n` 前缀。
- `connect_timeout` / `strict_host_keys`：连接超时、是否严格校验 host key。

**用环境变量传密码**（推荐）：变量名是 `SERVERS_MCP_PASSWORD_<名字大写、非字母数字转下划线>`：

```bash
export SERVERS_MCP_PASSWORD_STAGING_1="你的密码"   # 对应 name: "staging-1"
```

**先验证配置**（不连服务器，仅检查 JSON 是否合法）：

```bash
python -m mcp_server --check
# 或 python -m mcp_server --list
```

---

## 5. 把它接到 Claude 上（三种方式任选）

> 用绝对路径最稳。下面把 `/path/to/MCP_Server` 换成你的仓库真实路径，`/path/to/MCP_Server/.venv/bin/python` 换成上面虚拟环境里的 python。

### 方式 A：Claude Code（命令行）

```bash
claude mcp add fleet \
  --env PYTHONPATH=/path/to/MCP_Server \
  --env SERVERS_MCP_CONFIG=/path/to/MCP_Server/servers.json \
  --env SERVERS_MCP_READONLY=1 \
  -- /path/to/MCP_Server/.venv/bin/python -m mcp_server
```

加好后在 Claude Code 里 `/mcp` 就能看到 `fleet`，直接说「列出所有服务器」「看看 web-1 的磁盘」即可。
（`SERVERS_MCP_READONLY=1` 先只读试跑，确认无误后去掉这行即可开放变更。）

也可以把项目级配置写进仓库根目录的 `.mcp.json`（已附 `.mcp.json.example`，复制成 `.mcp.json` 并改路径）。

### 方式 B：Claude Desktop（桌面版）

编辑配置文件（macOS 在 `~/Library/Application Support/Claude/claude_desktop_config.json`，Windows 在 `%APPDATA%\Claude\claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "fleet": {
      "command": "/path/to/MCP_Server/.venv/bin/python",
      "args": ["-m", "mcp_server"],
      "env": {
        "PYTHONPATH": "/path/to/MCP_Server",
        "SERVERS_MCP_CONFIG": "/path/to/MCP_Server/servers.json",
        "SERVERS_MCP_READONLY": "1"
      }
    }
  }
}
```

保存后重启 Claude Desktop，工具栏里会出现 `fleet` 的工具。

### 方式 C：Claude Agent SDK（自己写的 Agent 程序）

```python
# pip install claude-agent-sdk
import asyncio
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

options = ClaudeAgentOptions(
    mcp_servers={
        "fleet": {
            "command": "/path/to/MCP_Server/.venv/bin/python",
            "args": ["-m", "mcp_server"],
            "env": {
                "PYTHONPATH": "/path/to/MCP_Server",
                "SERVERS_MCP_CONFIG": "/path/to/MCP_Server/servers.json",
            },
        }
    },
    allowed_tools=[
        "mcp__fleet__servers_list", "mcp__fleet__servers_health",
        "mcp__fleet__servers_status", "mcp__fleet__servers_run",
        "mcp__fleet__servers_run_group", "mcp__fleet__servers_service",
        "mcp__fleet__servers_logs",
    ],
)

async def main():
    async with ClaudeSDKClient(options=options) as client:
        await client.query("检查所有 prod 服务器的健康状态，有异常的把 nginx 重启一下")
        async for msg in client.receive_response():
            print(msg)

asyncio.run(main())
```

---

## 6. 远程 / 多人共享：HTTP 传输

上面是本地 stdio（Claude 把 Server 当子进程拉起，最简单）。如果要一个常驻、多客户端共享的服务：

```bash
python -m mcp_server --http --host 127.0.0.1 --port 8000
# 服务地址： http://127.0.0.1:8000/mcp
```

对外网暴露前，请放在反向代理 + 鉴权之后，并只绑定内网地址。客户端按各自的「HTTP/streamable MCP」方式填这个 URL 即可。

---

## 7. 安全须知

- **密钥不入库**：`servers.json` 已在 `.gitignore`；密码优先用 `SERVERS_MCP_PASSWORD_*` 环境变量。
- **先只读**：首次接入建议 `SERVERS_MCP_READONLY=1`，此时所有会改动服务器的工具都会被拒绝，只能查看。确认无误再放开。
- **危险命令拦截**：`servers.json` 的 `defaults.deny_patterns` 是一组正则，命中就拒绝执行（示例已内置 `rm -rf /`、fork 炸弹、`mkfs`、`dd of=/dev/*` 等）。按需增删。
- **最小权限**：给 Claude 用的 SSH 账号只授予必要权限；需要 root 的操作用 `use_sudo` + 受限 sudoers 白名单，而不是直接开放 root。
- **host key**：跨网首次连接默认 `AutoAdd`；对安全敏感的机器把该服务器 `strict_host_keys` 设为 true，并预先把它加入 `known_hosts`。

---

## 8. 常见用法示例（直接对 Claude 说）

- 「列出所有服务器」→ `servers_list`
- 「所有 prod 机器健康吗？」→ `servers_health(selector="prod")`
- 「web-1 磁盘和内存什么情况」→ `servers_status(name="web-1")`
- 「给所有 web 机器执行 `apt-get update`」→ `servers_run_group(selector="web", command="apt-get update")`
- 「重启 app-1 的 docker」→ `servers_service(name="app-1", service="docker", action="restart")`
- 「看 db-1 最近 200 行 mysql 日志」→ `servers_logs(name="db-1", unit="mysql", lines=200)`

---

## 9. 测试

离线单元测试（不联网、不需要真实服务器）：

```bash
python tests/test_mcp_server.py
# 或 python -m pytest tests/test_mcp_server.py -q
```
