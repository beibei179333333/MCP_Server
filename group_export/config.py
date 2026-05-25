"""Configuration loading. Token resolution order: CLI > env > file.

The token is a secret and is never read from committed source. Provide it via:
  * --token "<jwt>"
  * env GROUP_EXPORT_TOKEN
  * a local file (default: ./token.txt or $GROUP_EXPORT_TOKEN_FILE), gitignored
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

DEFAULT_BASE_URL = "http://fun-stat-bot.net"
DEFAULT_TOKEN_FILE = "token.txt"
ENV_TOKEN = "GROUP_EXPORT_TOKEN"
ENV_TOKEN_FILE = "GROUP_EXPORT_TOKEN_FILE"
ENV_BASE_URL = "GROUP_EXPORT_BASE_URL"


def resolve_token(cli_token: Optional[str]) -> Optional[str]:
    if cli_token:
        return cli_token.strip()
    env = os.environ.get(ENV_TOKEN)
    if env:
        return env.strip()
    path = os.environ.get(ENV_TOKEN_FILE, DEFAULT_TOKEN_FILE)
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None


def resolve_base_url(cli_base: Optional[str]) -> str:
    return (cli_base or os.environ.get(ENV_BASE_URL) or DEFAULT_BASE_URL).rstrip("/")


def load_config_file(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
