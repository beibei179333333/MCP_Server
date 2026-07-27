"""FastMCP tool layer exposing the fleet to an MCP client (e.g. Claude).

Tools (all prefixed ``servers_`` to avoid collisions with other MCP servers):

  read-only : servers_list, servers_health, servers_status, servers_logs
  mutating  : servers_run, servers_run_group, servers_service

The manager (and therefore the inventory) is loaded lazily on first use so the
server still starts and reports a helpful message when the config is missing.
"""
from __future__ import annotations

import json
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field
from mcp.server.fastmcp import FastMCP

from .manager import FleetError, ServerManager

SERVER_INSTRUCTIONS = (
    "Manage a fleet of SSH-reachable servers. Start with servers_list to see what "
    "is configured, servers_health / servers_status to inspect, then servers_run / "
    "servers_run_group / servers_service to make changes. Targets are selected by "
    "server name, by tag, or the literal 'all'."
)

mcp = FastMCP("servers_mcp", instructions=SERVER_INSTRUCTIONS)

_manager: Optional[ServerManager] = None
_load_error: Optional[str] = None


def get_manager() -> ServerManager:
    """Lazily build (and cache) the manager, raising FleetError with guidance."""
    global _manager, _load_error
    if _manager is not None:
        return _manager
    try:
        _manager = ServerManager.from_config()
        _load_error = None
        return _manager
    except Exception as exc:  # FileNotFoundError / ValueError / ImportError
        _load_error = str(exc)
        raise FleetError(_load_error) from exc


def reset_manager() -> None:
    """Test hook: drop the cached manager so the next call reloads config."""
    global _manager, _load_error
    _manager = None
    _load_error = None


class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def _err(exc: Exception) -> str:
    return f"Error: {exc}"


def _exec_markdown(d: dict[str, Any]) -> list[str]:
    """Render a single command/exec result dict as markdown lines."""
    status = "✅ ok" if d.get("ok") else "❌ failed"
    head = f"**{d.get('server')}** — {status}"
    if d.get("exit_status") is not None:
        head += f" (exit {d['exit_status']}, {d.get('duration_s', 0)}s)"
    lines = [head]
    if d.get("error"):
        lines.append(f"- error: {d['error']}")
    if d.get("stdout"):
        lines.append("```\n" + d["stdout"].rstrip() + "\n```")
    if d.get("stderr"):
        lines.append("stderr:\n```\n" + d["stderr"].rstrip() + "\n```")
    return lines


# ---- input models -----------------------------------------------------------
class ListInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    tag: Optional[str] = Field(default=None, description="Only list servers carrying this tag (e.g. 'web', 'prod').")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")


class SelectorInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    selector: str = Field(..., description="Server name, tag, comma-separated list, or 'all'.", min_length=1)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")


class StatusInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(..., description="Exact server name (from servers_list).", min_length=1)
    timeout: int = Field(default=20, description="Seconds to wait for the status command.", ge=1, le=120)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")


class RunInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(..., description="Exact server name to run the command on.", min_length=1)
    command: str = Field(..., description="Shell command to execute remotely, e.g. 'df -h' or 'systemctl restart nginx'.", min_length=1)
    timeout: int = Field(default=60, description="Seconds to wait for the command.", ge=1, le=600)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")


class RunGroupInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    selector: str = Field(..., description="Server name, tag, comma-separated list, or 'all'.", min_length=1)
    command: str = Field(..., description="Shell command to run on every matched server.", min_length=1)
    timeout: int = Field(default=60, description="Per-server timeout in seconds.", ge=1, le=600)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")


class ServiceInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(..., description="Exact server name.", min_length=1)
    service: str = Field(..., description="systemd unit name, e.g. 'nginx' or 'docker'.", min_length=1)
    action: str = Field(..., description="One of: status, start, stop, restart, reload, is-active, is-enabled.")
    timeout: int = Field(default=30, description="Seconds to wait.", ge=1, le=300)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")


class LogsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(..., description="Exact server name.", min_length=1)
    path: Optional[str] = Field(default=None, description="Log file to tail, e.g. '/var/log/nginx/error.log'.")
    unit: Optional[str] = Field(default=None, description="systemd unit to read with journalctl, e.g. 'nginx'. Use instead of 'path'.")
    lines: int = Field(default=100, description="Number of trailing lines (1-2000).", ge=1, le=2000)
    timeout: int = Field(default=20, description="Seconds to wait.", ge=1, le=120)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="'markdown' or 'json'.")


# ---- tools ------------------------------------------------------------------
@mcp.tool(
    name="servers_list",
    annotations={"title": "List configured servers", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def servers_list(params: ListInput) -> str:
    """List the servers defined in the inventory, optionally filtered by tag.

    Read-only. No secrets are returned — only name, host, port, user, tags, the
    configured auth method, and any health URL.

    Args:
        params (ListInput):
            - tag (Optional[str]): only servers carrying this tag.
            - response_format (str): 'markdown' (default) or 'json'.

    Returns:
        str: markdown table/list or a JSON array of
        {name, host, port, user, tags, health_url, auth, use_sudo, description}.
        On failure: "Error: <message>" (e.g. inventory file missing).
    """
    try:
        mgr = get_manager()
        servers = mgr.list_servers(tag=params.tag)
    except Exception as exc:
        return _err(exc)
    if not servers:
        return "No servers matched." if params.tag else "No servers configured."
    if params.response_format == ResponseFormat.JSON:
        return _json({"count": len(servers), "servers": servers})
    lines = [f"# Fleet ({len(servers)} server{'s' if len(servers) != 1 else ''})", ""]
    for s in servers:
        tags = f" [{', '.join(s['tags'])}]" if s["tags"] else ""
        lines.append(f"- **{s['name']}**{tags} — `{s['user']}@{s['host']}:{s['port']}` · auth: {s['auth']}"
                     + (f" · health: {s['health_url']}" if s.get("health_url") else ""))
        if s.get("description"):
            lines.append(f"  - {s['description']}")
    return "\n".join(lines)


@mcp.tool(
    name="servers_health",
    annotations={"title": "Health-check servers", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def servers_health(params: SelectorInput) -> str:
    """Check reachability of one or more servers: SSH TCP port plus optional HTTP probe.

    Read-only. Does not open an SSH session; only checks that the SSH port accepts
    a TCP connection and, when a health_url is configured, that it returns 2xx/3xx.

    Args:
        params (SelectorInput):
            - selector (str): server name, tag, comma list, or 'all'.
            - response_format (str): 'markdown' (default) or 'json'.

    Returns:
        str: per-server {ssh_port_open, http_ok?, http_status?, healthy}. On
        failure: "Error: <message>".
    """
    try:
        mgr = get_manager()
        results = await mgr.check_health_many(params.selector)
    except (FleetError, KeyError) as exc:
        return _err(exc)
    except Exception as exc:
        return _err(exc)
    if params.response_format == ResponseFormat.JSON:
        healthy = sum(1 for r in results if r.get("healthy"))
        return _json({"count": len(results), "healthy": healthy, "results": results})
    lines = ["# Health check", ""]
    for r in results:
        mark = "✅" if r.get("healthy") else "❌"
        extra = ""
        if "http_ok" in r:
            extra = f" · http: {'✅' if r['http_ok'] else '❌'} {r.get('http_detail', '')}"
        lines.append(f"- {mark} **{r['server']}** ({r['host']}) — ssh: {r['ssh_detail']}{extra}")
    return "\n".join(lines)


@mcp.tool(
    name="servers_status",
    annotations={"title": "Server status snapshot", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def servers_status(params: StatusInput) -> str:
    """Collect a status snapshot (uptime, load, cpus, memory, disk, top processes) over SSH.

    Read-only: runs a single bundled command that only reads system info.

    Args:
        params (StatusInput):
            - name (str): exact server name.
            - timeout (int): seconds, 1-120 (default 20).
            - response_format (str): 'markdown' (default) or 'json'.

    Returns:
        str: markdown with a section per metric, or JSON
        {server, ok, exit_status, sections:{host,uptime,load,cpus,mem,disk,top}, ...}.
        On failure (unreachable / auth): the result carries ok=false and an 'error'.
    """
    try:
        mgr = get_manager()
        res = await mgr.get_status(params.name, timeout=params.timeout)
    except (FleetError, KeyError) as exc:
        return _err(exc)
    if params.response_format == ResponseFormat.JSON:
        return _json(res)
    if not res.get("ok"):
        return f"❌ **{params.name}** unreachable: {res.get('error') or res.get('stderr') or 'unknown error'}"
    sec = res.get("sections", {})
    lines = [f"# {params.name} status", ""]
    for key in ("host", "uptime", "load", "cpus", "mem", "disk", "top"):
        if sec.get(key):
            lines.append(f"**{key}**\n```\n{sec[key]}\n```")
    return "\n".join(lines)


@mcp.tool(
    name="servers_run",
    annotations={"title": "Run a command on one server", "readOnlyHint": False,
                 "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
)
async def servers_run(params: RunInput) -> str:
    """Run an arbitrary shell command on ONE server over SSH.

    Mutating and potentially destructive: whatever the command does happens on the
    remote host. Blocked when the server is in read-only mode or the command
    matches a configured deny pattern.

    Args:
        params (RunInput):
            - name (str): exact server name.
            - command (str): shell command, e.g. 'apt-get update', 'df -h'.
            - timeout (int): seconds, 1-600 (default 60).
            - response_format (str): 'markdown' (default) or 'json'.

    Returns:
        str: {server, ok, exit_status, stdout, stderr, duration_s} rendered as
        markdown or JSON. On refusal/unknown server: "Error: <message>".
    """
    try:
        mgr = get_manager()
        res = await mgr.run_command(params.name, params.command, timeout=params.timeout)
    except (FleetError, KeyError) as exc:
        return _err(exc)
    if params.response_format == ResponseFormat.JSON:
        return _json(res)
    return "\n".join(_exec_markdown(res))


@mcp.tool(
    name="servers_run_group",
    annotations={"title": "Run a command across a group", "readOnlyHint": False,
                 "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
)
async def servers_run_group(params: RunGroupInput) -> str:
    """Run the SAME command on every server matched by a selector, concurrently.

    Mutating and potentially destructive, applied to MULTIPLE hosts at once — use
    a tag or 'all' deliberately. Honors read-only mode and deny patterns.

    Args:
        params (RunGroupInput):
            - selector (str): name, tag, comma list, or 'all'.
            - command (str): shell command to run everywhere.
            - timeout (int): per-server seconds, 1-600 (default 60).
            - response_format (str): 'markdown' (default) or 'json'.

    Returns:
        str: {selector, command, count, succeeded, failed, results:[...]} as
        markdown or JSON. On refusal/no match: "Error: <message>".
    """
    try:
        mgr = get_manager()
        res = await mgr.run_on_group(params.selector, params.command, timeout=params.timeout)
    except (FleetError, KeyError) as exc:
        return _err(exc)
    if params.response_format == ResponseFormat.JSON:
        return _json(res)
    lines = [f"# `{res['command']}` on `{res['selector']}`",
             f"{res['succeeded']}/{res['count']} succeeded, {res['failed']} failed", ""]
    for d in res["results"]:
        lines.extend(_exec_markdown(d))
        lines.append("")
    return "\n".join(lines).rstrip()


@mcp.tool(
    name="servers_service",
    annotations={"title": "Control a systemd service", "readOnlyHint": False,
                 "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
)
async def servers_service(params: ServiceInput) -> str:
    """Query or control a systemd service on one server (systemctl <action> <service>).

    'status', 'is-active' and 'is-enabled' are read-only; 'start', 'stop',
    'restart' and 'reload' change state and are blocked in read-only mode. If the
    server sets use_sudo, the command is prefixed with 'sudo -n'.

    Args:
        params (ServiceInput):
            - name (str): exact server name.
            - service (str): unit name, e.g. 'nginx'.
            - action (str): status|start|stop|restart|reload|is-active|is-enabled.
            - timeout (int): seconds, 1-300 (default 30).
            - response_format (str): 'markdown' (default) or 'json'.

    Returns:
        str: {server, service, action, ok, exit_status, stdout, stderr} as
        markdown or JSON. On bad action / read-only refusal: "Error: <message>".
    """
    try:
        mgr = get_manager()
        res = await mgr.service_action(params.name, params.service, params.action, timeout=params.timeout)
    except (FleetError, KeyError) as exc:
        return _err(exc)
    if params.response_format == ResponseFormat.JSON:
        return _json(res)
    lines = [f"# {params.action} {params.service} on {params.name}"]
    lines.extend(_exec_markdown(res))
    return "\n".join(lines)


@mcp.tool(
    name="servers_logs",
    annotations={"title": "Tail server logs", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def servers_logs(params: LogsInput) -> str:
    """Tail the last N lines of a log file, or a systemd unit's journal, over SSH.

    Read-only. Provide exactly one of 'path' (a file) or 'unit' (journalctl -u).

    Args:
        params (LogsInput):
            - name (str): exact server name.
            - path (Optional[str]): log file path.
            - unit (Optional[str]): systemd unit for journalctl.
            - lines (int): trailing lines, 1-2000 (default 100).
            - timeout (int): seconds, 1-120 (default 20).
            - response_format (str): 'markdown' (default) or 'json'.

    Returns:
        str: {server, ok, exit_status, stdout, stderr} as markdown or JSON.
        On missing path/unit or unknown server: "Error: <message>".
    """
    try:
        mgr = get_manager()
        res = await mgr.tail_logs(
            params.name, path=params.path, unit=params.unit,
            lines=params.lines, timeout=params.timeout,
        )
    except (FleetError, KeyError) as exc:
        return _err(exc)
    if params.response_format == ResponseFormat.JSON:
        return _json(res)
    return "\n".join(_exec_markdown(res))
