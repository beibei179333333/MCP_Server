"""Load and validate the fleet inventory (the list of servers to manage).

Design goals:
  * No network and no MCP-SDK imports here, so it stays trivially unit-testable.
  * Secrets (passwords) are NEVER required to live in the committed file: they can
    be supplied per-server via an environment variable, which is the recommended
    path. Key-based auth needs no secret in the file at all.

Config file shape (JSON)::

    {
      "defaults": { "user": "root", "port": 22, "key_file": "~/.ssh/id_ed25519" },
      "servers": [
        { "name": "web-1", "host": "10.0.0.11", "tags": ["web", "prod"],
          "health_url": "http://10.0.0.11/healthz" },
        ...
      ]
    }

Resolution order for the config path:
    explicit arg  >  $SERVERS_MCP_CONFIG  >  ./servers.json  >  ~/.config/servers-mcp/servers.json
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ---- environment / path conventions ----------------------------------------
ENV_CONFIG = "SERVERS_MCP_CONFIG"
ENV_READONLY = "SERVERS_MCP_READONLY"
ENV_BACKEND = "SERVERS_MCP_BACKEND"          # auto | paramiko | ssh
ENV_PASSWORD_PREFIX = "SERVERS_MCP_PASSWORD_"  # + SANITIZED_NAME

DEFAULT_CONFIG_PATHS = [
    "servers.json",
    "~/.config/servers-mcp/servers.json",
]

# Field defaults applied when neither the server entry nor the "defaults" block set them.
_BUILTIN_DEFAULTS: dict[str, Any] = {
    "port": 22,
    "user": "root",
    "connect_timeout": 10,
    "use_sudo": False,
    "strict_host_keys": False,
}

# Keys allowed in a server entry (anything else is a config typo we should flag).
_SERVER_KEYS = {
    "name", "host", "port", "user", "key_file", "password",
    "tags", "health_url", "connect_timeout", "use_sudo",
    "strict_host_keys", "description",
}


def _sanitize_env_name(name: str) -> str:
    """Map a server name to the suffix used in ``SERVERS_MCP_PASSWORD_<NAME>``.

    Non-alphanumeric characters become ``_`` and the whole thing is upper-cased,
    so ``web-1`` -> ``WEB_1`` -> ``SERVERS_MCP_PASSWORD_WEB_1``.
    """
    return re.sub(r"[^A-Za-z0-9]", "_", name).upper()


@dataclass
class Server:
    """A single managed server. ``password`` is resolved at load time and is a
    secret — it is deliberately excluded from :meth:`public_dict`."""

    name: str
    host: str
    port: int = 22
    user: str = "root"
    key_file: Optional[str] = None
    password: Optional[str] = field(default=None, repr=False)
    tags: list[str] = field(default_factory=list)
    health_url: Optional[str] = None
    connect_timeout: int = 10
    use_sudo: bool = False
    strict_host_keys: bool = False
    description: str = ""

    def public_dict(self) -> dict[str, Any]:
        """Serializable view with no secrets, safe to hand back to the client."""
        return {
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "tags": list(self.tags),
            "health_url": self.health_url,
            "auth": "password" if self.password else ("key" if self.key_file else "agent/default"),
            "use_sudo": self.use_sudo,
            "description": self.description,
        }


@dataclass
class Inventory:
    servers: list[Server]
    deny_patterns: list[str] = field(default_factory=list)
    read_only: bool = False
    backend: str = "auto"
    source_path: Optional[str] = None

    # ---- lookups -----------------------------------------------------------
    def by_name(self, name: str) -> Optional[Server]:
        for s in self.servers:
            if s.name == name:
                return s
        return None

    def resolve_targets(self, selector: str) -> list[Server]:
        """Turn a selector into a concrete server list.

        ``selector`` may be:
          * ``"all"``           -> every server
          * an exact server name -> that one server
          * a tag                -> every server carrying that tag
          * comma-separated combination of any of the above

        Raises ``KeyError`` with an actionable message when nothing matches, so
        the tool layer can surface it verbatim.
        """
        wanted: list[Server] = []
        seen: set[str] = set()

        def add(s: Server) -> None:
            if s.name not in seen:
                seen.add(s.name)
                wanted.append(s)

        for raw in (selector or "").split(","):
            token = raw.strip()
            if not token:
                continue
            if token == "all":
                for s in self.servers:
                    add(s)
                continue
            named = self.by_name(token)
            if named is not None:
                add(named)
                continue
            tagged = [s for s in self.servers if token in s.tags]
            if tagged:
                for s in tagged:
                    add(s)
                continue
            names = ", ".join(s.name for s in self.servers) or "(none configured)"
            tags = ", ".join(sorted({t for s in self.servers for t in s.tags})) or "(none)"
            raise KeyError(
                f"no server matched '{token}'. Known names: {names}. "
                f"Known tags: {tags}. Use 'all' to target every server."
            )
        if not wanted:
            raise KeyError("empty selector — pass a server name, a tag, or 'all'.")
        return wanted


# ---- loading ----------------------------------------------------------------
def _find_config_path(explicit: Optional[str]) -> Optional[str]:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    env = os.environ.get(ENV_CONFIG)
    if env:
        candidates.append(env)
    candidates.extend(DEFAULT_CONFIG_PATHS)
    for c in candidates:
        p = Path(c).expanduser()
        if p.is_file():
            return str(p)
    return None


def _resolve_password(name: str, entry_password: Optional[str]) -> Optional[str]:
    """Env var wins over an in-file password so secrets can stay out of the file."""
    env_key = ENV_PASSWORD_PREFIX + _sanitize_env_name(name)
    return os.environ.get(env_key) or entry_password


def _bool_env(key: str) -> bool:
    return os.environ.get(key, "").strip().lower() in ("1", "true", "yes", "on")


def load_inventory(path: Optional[str] = None) -> Inventory:
    """Read, validate and return the fleet inventory.

    Raises ``FileNotFoundError`` if no config is found and ``ValueError`` for a
    malformed one — both carry messages meant to be shown to the user as-is.
    """
    resolved = _find_config_path(path)
    if resolved is None:
        looked = [path] if path else []
        looked += [os.environ.get(ENV_CONFIG, "")] + DEFAULT_CONFIG_PATHS
        looked = [x for x in looked if x]
        raise FileNotFoundError(
            "no inventory file found. Create 'servers.json' (see servers.example.json) "
            f"or set ${ENV_CONFIG}. Looked in: {', '.join(looked)}"
        )

    try:
        with open(resolved, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{resolved} is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"{resolved}: top-level value must be a JSON object.")

    defaults = {**_BUILTIN_DEFAULTS, **(raw.get("defaults") or {})}
    entries = raw.get("servers")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{resolved}: 'servers' must be a non-empty list.")

    servers: list[Server] = []
    names: set[str] = set()
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"{resolved}: servers[{i}] must be an object.")
        unknown = set(entry) - _SERVER_KEYS
        if unknown:
            raise ValueError(
                f"{resolved}: servers[{i}] has unknown key(s): {', '.join(sorted(unknown))}. "
                f"Allowed: {', '.join(sorted(_SERVER_KEYS))}."
            )
        merged: dict[str, Any] = {
            k: v for k, v in defaults.items() if k in _SERVER_KEYS
        }
        merged.update(entry)

        name = merged.get("name")
        host = merged.get("host")
        if not name or not isinstance(name, str):
            raise ValueError(f"{resolved}: servers[{i}] is missing a string 'name'.")
        if not host or not isinstance(host, str):
            raise ValueError(f"{resolved}: server '{name}' is missing a string 'host'.")
        if name in names:
            raise ValueError(f"{resolved}: duplicate server name '{name}'.")
        names.add(name)

        key_file = merged.get("key_file")
        if key_file:
            key_file = str(Path(str(key_file)).expanduser())

        servers.append(
            Server(
                name=name,
                host=host,
                port=int(merged.get("port", 22)),
                user=str(merged.get("user", "root")),
                key_file=key_file,
                password=_resolve_password(name, merged.get("password")),
                tags=list(merged.get("tags") or []),
                health_url=merged.get("health_url"),
                connect_timeout=int(merged.get("connect_timeout", 10)),
                use_sudo=bool(merged.get("use_sudo", False)),
                strict_host_keys=bool(merged.get("strict_host_keys", False)),
                description=str(merged.get("description", "")),
            )
        )

    backend = os.environ.get(ENV_BACKEND) or raw.get("backend") or "auto"
    if backend not in ("auto", "paramiko", "ssh"):
        raise ValueError(f"{resolved}: backend must be one of auto|paramiko|ssh, got '{backend}'.")

    read_only = _bool_env(ENV_READONLY) or bool(raw.get("read_only", False))
    deny = list((raw.get("defaults") or {}).get("deny_patterns") or raw.get("deny_patterns") or [])

    return Inventory(
        servers=servers,
        deny_patterns=[str(p) for p in deny],
        read_only=read_only,
        backend=str(backend),
        source_path=resolved,
    )
