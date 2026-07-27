"""High-level fleet operations, independent of the MCP SDK.

Every method returns plain ``dict`` / ``list`` structures (no MCP types), so the
manager can be exercised directly in unit tests with a fake backend. The MCP tool
layer in :mod:`mcp_server.server` is a thin wrapper that formats these results.
"""
from __future__ import annotations

import asyncio
import re
import shlex
from typing import Any, Optional

from .backends import ExecResult, SSHBackend, build_service_command, get_backend
from .inventory import Inventory, Server, load_inventory

# One shell snippet gathers everything ``status`` needs in a single round-trip.
_STATUS_SNIPPET = (
    "echo '# host'; hostname; "
    "echo '# uptime'; uptime; "
    "echo '# load'; cat /proc/loadavg 2>/dev/null; "
    "echo '# cpus'; nproc 2>/dev/null; "
    "echo '# mem'; (free -h 2>/dev/null || vm_stat 2>/dev/null); "
    "echo '# disk'; df -h / 2>/dev/null; "
    "echo '# top'; (ps -eo pcpu,pmem,comm --sort=-pcpu 2>/dev/null | head -6)"
)

_SERVICE_ACTIONS = {"status", "start", "stop", "restart", "reload", "is-active", "is-enabled"}
_READONLY_SERVICE_ACTIONS = {"status", "is-active", "is-enabled"}


class FleetError(Exception):
    """Raised for user-correctable problems; the message is safe to surface."""


class ServerManager:
    def __init__(self, inventory: Inventory, backend: Optional[SSHBackend] = None) -> None:
        self.inv = inventory
        self.backend = backend or get_backend(inventory.backend)
        self._deny = [re.compile(p) for p in inventory.deny_patterns]

    @classmethod
    def from_config(cls, path: Optional[str] = None) -> "ServerManager":
        return cls(load_inventory(path))

    # ---- guards ------------------------------------------------------------
    def _ensure_writable(self, what: str) -> None:
        if self.inv.read_only:
            raise FleetError(
                f"refusing to {what}: server is in read-only mode "
                "(unset SERVERS_MCP_READONLY or read_only in the config to allow changes)."
            )

    def _check_command(self, command: str) -> None:
        for pat in self._deny:
            if pat.search(command):
                raise FleetError(
                    f"command blocked by deny pattern /{pat.pattern}/. "
                    "Edit deny_patterns in the config if this is intended."
                )

    def _target(self, name: str) -> Server:
        s = self.inv.by_name(name)
        if s is None:
            known = ", ".join(x.name for x in self.inv.servers) or "(none)"
            raise FleetError(f"unknown server '{name}'. Configured servers: {known}.")
        return s

    # ---- read-only ---------------------------------------------------------
    def list_servers(self, tag: Optional[str] = None) -> list[dict[str, Any]]:
        servers = self.inv.servers
        if tag:
            servers = [s for s in servers if tag in s.tags]
        return [s.public_dict() for s in servers]

    async def check_health(self, server: Server) -> dict[str, Any]:
        """TCP reachability of the SSH port plus an optional HTTP health probe."""
        tcp_ok, tcp_detail = await _tcp_probe(server.host, server.port, server.connect_timeout)
        result: dict[str, Any] = {
            "server": server.name,
            "host": server.host,
            "ssh_port_open": tcp_ok,
            "ssh_detail": tcp_detail,
        }
        if server.health_url:
            http_ok, status, detail = await _http_probe(server.health_url, server.connect_timeout)
            result["health_url"] = server.health_url
            result["http_ok"] = http_ok
            result["http_status"] = status
            result["http_detail"] = detail
            result["healthy"] = tcp_ok and http_ok
        else:
            result["healthy"] = tcp_ok
        return result

    async def check_health_many(self, selector: str) -> list[dict[str, Any]]:
        targets = self.inv.resolve_targets(selector)
        return await asyncio.gather(*(self.check_health(s) for s in targets))

    async def get_status(self, name: str, timeout: int = 20) -> dict[str, Any]:
        server = self._target(name)
        res = await self.backend.execute(server, _STATUS_SNIPPET, timeout)
        parsed = _parse_status(res.stdout) if res.ok else {}
        out = res.to_dict()
        out["sections"] = parsed
        return out

    async def tail_logs(
        self, name: str, path: Optional[str] = None, unit: Optional[str] = None,
        lines: int = 100, timeout: int = 20,
    ) -> dict[str, Any]:
        server = self._target(name)
        lines = max(1, min(int(lines), 2000))
        if unit:
            prefix = "sudo -n " if server.use_sudo else ""
            command = f"{prefix}journalctl -u {shlex.quote(unit)} -n {lines} --no-pager"
        elif path:
            command = f"tail -n {lines} {shlex.quote(path)}"
        else:
            raise FleetError("provide either 'path' (a log file) or 'unit' (a systemd unit).")
        res = await self.backend.execute(server, command, timeout)
        return res.to_dict()

    # ---- mutating ----------------------------------------------------------
    async def run_command(self, name: str, command: str, timeout: int = 60) -> dict[str, Any]:
        command = (command or "").strip()
        if not command:
            raise FleetError("command must not be empty.")
        self._ensure_writable("run a command")
        self._check_command(command)
        server = self._target(name)
        res = await self.backend.execute(server, command, timeout)
        return res.to_dict()

    async def run_on_group(self, selector: str, command: str, timeout: int = 60) -> dict[str, Any]:
        command = (command or "").strip()
        if not command:
            raise FleetError("command must not be empty.")
        self._ensure_writable("run a command")
        self._check_command(command)
        targets = self.inv.resolve_targets(selector)
        results: list[ExecResult] = await asyncio.gather(
            *(self.backend.execute(s, command, timeout) for s in targets)
        )
        dicts = [r.to_dict() for r in results]
        return {
            "selector": selector,
            "command": command,
            "count": len(dicts),
            "succeeded": sum(1 for r in results if r.ok),
            "failed": sum(1 for r in results if not r.ok),
            "results": dicts,
        }

    async def service_action(
        self, name: str, service: str, action: str, timeout: int = 30,
    ) -> dict[str, Any]:
        action = (action or "").strip()
        if action not in _SERVICE_ACTIONS:
            raise FleetError(
                f"unsupported service action '{action}'. "
                f"Allowed: {', '.join(sorted(_SERVICE_ACTIONS))}."
            )
        if action not in _READONLY_SERVICE_ACTIONS:
            self._ensure_writable(f"{action} a service")
        server = self._target(name)
        command = build_service_command(action, service, server.use_sudo)
        res = await self.backend.execute(server, command, timeout)
        out = res.to_dict()
        out["service"] = service
        out["action"] = action
        return out


# ---- probes & parsing (module-level, easily testable) -----------------------
async def _tcp_probe(host: str, port: int, timeout: int) -> tuple[bool, str]:
    try:
        fut = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(fut, timeout=timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True, f"tcp {host}:{port} reachable"
    except asyncio.TimeoutError:
        return False, f"tcp {host}:{port} timed out after {timeout}s"
    except OSError as exc:
        return False, f"tcp {host}:{port} failed: {exc}"


async def _http_probe(url: str, timeout: int) -> tuple[bool, Optional[int], str]:
    try:
        import httpx
    except ImportError:
        return False, None, "httpx not installed (pip install httpx) — cannot run HTTP health check."
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            resp = await client.get(url)
        ok = 200 <= resp.status_code < 400
        return ok, resp.status_code, f"HTTP {resp.status_code}"
    except Exception as exc:  # httpx raises a family of connect/timeout errors
        return False, None, f"{type(exc).__name__}: {exc}"


def _parse_status(text: str) -> dict[str, str]:
    """Split the ``_STATUS_SNIPPET`` output into ``{section: body}`` blocks."""
    sections: dict[str, str] = {}
    current = None
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("# "):
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = line[2:].strip()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections
