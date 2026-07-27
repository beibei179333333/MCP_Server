"""Interactive local setup wizard: build servers.json without exposing secrets.

Run on YOUR machine (not in a shared/cloud session):

    python -m mcp_server init

It asks for each server's host / port / user / tags, takes the password with a
hidden prompt (getpass, no echo), and writes a local ``servers.json`` — which is
gitignored, so credentials never get committed. Passwords may instead be left to
environment variables (``SERVERS_MCP_PASSWORD_<NAME>``); the wizard can print the
matching export lines for you.

This module has no third-party imports so it runs before you install anything.
"""
from __future__ import annotations

import getpass
import json
import os
import re
from pathlib import Path
from typing import Any, Optional


def _ask(prompt: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default not in (None, "") else ""
    try:
        val = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        val = ""
    return val or (default or "")


def _ask_bool(prompt: str, default: bool = False) -> bool:
    d = "Y/n" if default else "y/N"
    val = _ask(f"{prompt} ({d})").lower()
    if not val:
        return default
    return val in ("y", "yes", "是", "true", "1")


def _sanitize_env_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", name).upper()


def run_wizard(path: str = "servers.json", force: bool = False) -> int:
    """Interactively build ``path``. Returns a process exit code."""
    target = Path(path)
    if target.exists() and not force:
        print(f"拒绝覆盖已存在的 {target}（如需覆盖请加 --force）。", flush=True)
        return 1

    print("=" * 60)
    print(" 服务器清单配置向导 (servers.json)")
    print(" 密码为隐藏输入，不会回显；servers.json 已被 .gitignore 忽略。")
    print("=" * 60)

    # ---- shared defaults to cut down on repetition ----
    print("\n先设置默认值（每台可单独覆盖）：")
    default_user = _ask("默认用户名", "root")
    default_port = _ask("默认 SSH 端口", "22")
    default_key = _ask("默认密钥文件（留空表示默认用密码认证）", "~/.ssh/id_ed25519")

    try:
        count = int(_ask("要配置几台服务器", "6") or "6")
    except ValueError:
        count = 6
    count = max(1, count)

    servers: list[dict[str, Any]] = []
    env_exports: list[str] = []
    used_names: set[str] = set()

    for i in range(1, count + 1):
        print(f"\n--- 第 {i}/{count} 台 ---")
        while True:
            name = _ask(f"名字（唯一，如 web-{i}）", f"server-{i}")
            if name in used_names:
                print("  名字重复了，换一个。")
                continue
            break
        used_names.add(name)

        host = _ask("主机 / IP")
        while not host:
            host = _ask("主机 / IP 不能为空，请输入")

        entry: dict[str, Any] = {"name": name, "host": host}

        port = _ask("端口", default_port)
        if port and port != "22":
            entry["port"] = int(port)
        user = _ask("用户名", default_user)
        if user and user != "root":
            entry["user"] = user

        tags = _ask("标签（逗号分隔，如 web,prod）", "")
        if tags:
            entry["tags"] = [t.strip() for t in tags.split(",") if t.strip()]

        # ---- auth ----
        auth = _ask("认证方式: key(密钥) / password(密码)", "key" if default_key else "password").lower()
        if auth.startswith("p"):
            store = _ask("密码存储: env(环境变量,更安全) / file(写入文件)", "env").lower()
            pw = getpass.getpass("  密码（输入不显示）: ")
            if store.startswith("f"):
                entry["password"] = pw
            else:
                env_key = "SERVERS_MCP_PASSWORD_" + _sanitize_env_name(name)
                env_exports.append(f'export {env_key}={_shell_quote(pw)}')
        else:
            key_file = _ask("密钥文件路径", default_key or "~/.ssh/id_ed25519")
            if key_file:
                entry["key_file"] = key_file

        if _ask_bool("需要 sudo 才能管理服务?", False):
            entry["use_sudo"] = True

        health = _ask("HTTP 健康检查 URL（可选，回车跳过）", "")
        if health:
            entry["health_url"] = health

        servers.append(entry)

    config: dict[str, Any] = {
        "defaults": {
            "user": default_user,
            "port": int(default_port or "22"),
            "connect_timeout": 10,
            "deny_patterns": [
                r"rm\s+-rf\s+/(\s|$)",
                r":\(\)\s*\{\s*:\|:&\s*\};:",
                r"mkfs",
                r"\bdd\b.*of=/dev/",
            ],
        },
        "read_only": False,
        "backend": "auto",
        "servers": servers,
    }
    if default_key:
        config["defaults"]["key_file"] = default_key

    with open(target, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")
    try:
        os.chmod(target, 0o600)  # tighten perms since it may hold a password
    except OSError:
        pass

    print("\n" + "=" * 60)
    print(f"✅ 已写入 {target}（权限 600），共 {len(servers)} 台。")

    if env_exports:
        env_path = target.parent / ".env.servers"
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("# source this before starting the MCP server; keep it private.\n")
            f.write("\n".join(env_exports) + "\n")
        try:
            os.chmod(env_path, 0o600)
        except OSError:
            pass
        print(f"🔐 {len(env_exports)} 个密码写入了 {env_path}（未进 servers.json）。")
        print(f"   启动前先： source {env_path}")

    print("\n下一步：")
    print("  python -m mcp_server --check     # 校验")
    print("  python -m mcp_server --list      # 查看清单")
    print("=" * 60)

    # sanity-load so obvious mistakes surface immediately
    try:
        from .inventory import load_inventory
        inv = load_inventory(str(target))
        print(f"（自检通过：成功解析 {len(inv.servers)} 台）")
    except Exception as exc:  # pragma: no cover - defensive
        print(f"⚠️ 自检未通过：{exc}")
        return 1
    return 0


def _shell_quote(s: str) -> str:
    """Single-quote a value for a POSIX shell export line."""
    return "'" + s.replace("'", "'\"'\"'") + "'"
