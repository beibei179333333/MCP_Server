"""Pluggable SSH execution backends.

Two interchangeable backends implement the same ``execute`` coroutine:

  * :class:`ParamikoBackend` – pure-Python SSH (``pip install paramiko``). Handles
    both key- and password-based auth. Blocking calls are pushed to a worker
    thread so a fan-out across the fleet still runs concurrently.
  * :class:`SystemSSHBackend` – shells out to the system ``ssh``. Zero Python
    dependency and reuses your ``~/.ssh/config`` and agent, but cannot do
    password auth (``BatchMode`` is forced to avoid interactive hangs).

:func:`get_backend` picks one; ``"auto"`` prefers paramiko when importable
because it is self-contained, otherwise falls back to system ``ssh``.
"""
from __future__ import annotations

import asyncio
import shlex
import time
from dataclasses import dataclass
from typing import Optional

from .inventory import Server


@dataclass
class ExecResult:
    """Outcome of one remote command."""

    server: str
    ok: bool                       # True iff the command ran AND exited 0
    exit_status: Optional[int]     # None when the connection/exec never completed
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None    # transport-level failure (auth, timeout, DNS…)
    duration_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "server": self.server,
            "ok": self.ok,
            "exit_status": self.exit_status,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error": self.error,
            "duration_s": round(self.duration_s, 3),
        }


class SSHBackend:
    """Interface implemented by the concrete backends."""

    name = "base"

    async def execute(self, server: Server, command: str, timeout: int) -> ExecResult:  # pragma: no cover
        raise NotImplementedError


# ---- paramiko ---------------------------------------------------------------
class ParamikoBackend(SSHBackend):
    name = "paramiko"

    def __init__(self) -> None:
        # Import lazily so merely importing this module never requires paramiko.
        import paramiko  # noqa: F401  (validated here, used in the worker)

    async def execute(self, server: Server, command: str, timeout: int) -> ExecResult:
        return await asyncio.to_thread(self._run_blocking, server, command, timeout)

    @staticmethod
    def _run_blocking(server: Server, command: str, timeout: int) -> ExecResult:
        import paramiko

        start = time.monotonic()
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        policy = paramiko.RejectPolicy() if server.strict_host_keys else paramiko.AutoAddPolicy()
        client.set_missing_host_key_policy(policy)
        try:
            connect_kwargs: dict = dict(
                hostname=server.host,
                port=server.port,
                username=server.user,
                timeout=server.connect_timeout,
                banner_timeout=server.connect_timeout,
                auth_timeout=server.connect_timeout,
                allow_agent=True,
                look_for_keys=server.key_file is None and server.password is None,
            )
            if server.key_file:
                connect_kwargs["key_filename"] = server.key_file
            if server.password:
                connect_kwargs["password"] = server.password
                connect_kwargs["look_for_keys"] = False
            client.connect(**connect_kwargs)

            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            status = stdout.channel.recv_exit_status()
            return ExecResult(
                server=server.name,
                ok=(status == 0),
                exit_status=status,
                stdout=out,
                stderr=err,
                duration_s=time.monotonic() - start,
            )
        except Exception as exc:  # convert every transport failure to a result
            return ExecResult(
                server=server.name,
                ok=False,
                exit_status=None,
                error=_describe_exc(exc),
                duration_s=time.monotonic() - start,
            )
        finally:
            try:
                client.close()
            except Exception:
                pass


# ---- system ssh -------------------------------------------------------------
class SystemSSHBackend(SSHBackend):
    name = "ssh"

    async def execute(self, server: Server, command: str, timeout: int) -> ExecResult:
        start = time.monotonic()
        if server.password:
            return ExecResult(
                server=server.name,
                ok=False,
                exit_status=None,
                error=("password auth is not supported by the system-ssh backend; "
                       "install paramiko (pip install paramiko) or switch to key-based auth."),
                duration_s=time.monotonic() - start,
            )
        argv = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={server.connect_timeout}",
            "-o", "StrictHostKeyChecking=" + ("yes" if server.strict_host_keys else "accept-new"),
            "-p", str(server.port),
        ]
        if server.key_file:
            argv += ["-i", server.key_file]
        argv += [f"{server.user}@{server.host}", "--", command]

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return ExecResult(
                server=server.name, ok=False, exit_status=None,
                error="the 'ssh' command was not found; install OpenSSH or use the paramiko backend.",
                duration_s=time.monotonic() - start,
            )
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ExecResult(
                server=server.name, ok=False, exit_status=None,
                error=f"command timed out after {timeout}s.",
                duration_s=time.monotonic() - start,
            )
        status = proc.returncode
        return ExecResult(
            server=server.name,
            ok=(status == 0),
            exit_status=status,
            stdout=out_b.decode("utf-8", "replace"),
            stderr=err_b.decode("utf-8", "replace"),
            duration_s=time.monotonic() - start,
        )


def _describe_exc(exc: Exception) -> str:
    """Turn a paramiko/socket exception into a short, actionable message."""
    name = type(exc).__name__
    msg = str(exc).strip()
    hints = {
        "AuthenticationException": "authentication failed — check user, key_file or password.",
        "NoValidConnectionsError": "could not open a connection — host/port unreachable or SSH not listening.",
        "SSHException": "SSH negotiation failed — check host key policy and server SSH config.",
        "timeout": "connection timed out — host unreachable or blocked by a firewall.",
    }
    for key, hint in hints.items():
        if key.lower() in name.lower() or key.lower() in msg.lower():
            return f"{name}: {msg or hint} ({hint})" if msg else f"{name}: {hint}"
    return f"{name}: {msg}" if msg else name


# ---- selection --------------------------------------------------------------
def get_backend(preference: str = "auto") -> SSHBackend:
    """Return a backend instance for ``preference`` (auto|paramiko|ssh).

    ``auto`` prefers paramiko (self-contained, supports passwords) and falls back
    to the system ``ssh`` when paramiko is not installed.
    """
    if preference == "ssh":
        return SystemSSHBackend()
    if preference == "paramiko":
        return ParamikoBackend()  # raises ImportError with a clear message if missing
    # auto
    try:
        return ParamikoBackend()
    except ImportError:
        return SystemSSHBackend()


def build_service_command(action: str, service: str, use_sudo: bool) -> str:
    """Compose a safe ``systemctl`` command line (service name is shell-quoted)."""
    prefix = "sudo -n " if use_sudo else ""
    return f"{prefix}systemctl {shlex.quote(action)} {shlex.quote(service)}"
