#!/usr/bin/env python3
"""Batch-rename the display title of Telegram custom-emoji sticker sets.

Every set listed in ``sets.txt`` (or a file you pass with ``--names-file``)
has its title changed to the same value (default: ``更多表情 @emojipd``) via the
Bot API method ``setStickerSetTitle``.

IMPORTANT
---------
``setStickerSetTitle`` only works for sets **owned by the calling bot**. All the
sets here end in ``_by_pindaobianjiqibot``, so you must use the token of the bot
**@pindaobianjiqibot**. Any other bot's token will get "STICKERSET_INVALID" /
"sticker set not found".

Token (any one of these, checked in this order):
  1. ``--token <BOT_TOKEN>``
  2. environment variable ``TELEGRAM_BOT_TOKEN``
  3. a ``token.txt`` file next to this script (git-ignored)

Usage
-----
    # dry run first — shows exactly what it would do, no network calls
    python telegram_emoji/rename_emoji_titles.py --dry-run

    # do it for real
    export TELEGRAM_BOT_TOKEN="123456:ABC..."
    python telegram_emoji/rename_emoji_titles.py

    # custom title / custom list
    python telegram_emoji/rename_emoji_titles.py --title "更多表情 @emojipd" \
        --names-file my_sets.txt
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_NAMES_FILE = os.path.join(HERE, "sets.txt")
DEFAULT_TOKEN_FILE = os.path.join(HERE, "token.txt")
DEFAULT_TITLE = "更多表情 @emojipd"
API_BASE = "https://api.telegram.org"

# Telegram limits sticker-set titles to 1-64 characters.
MAX_TITLE_LEN = 64


def load_token(cli_token: Optional[str]) -> str:
    if cli_token:
        return cli_token.strip()
    env = os.environ.get("TELEGRAM_BOT_TOKEN")
    if env and env.strip():
        return env.strip()
    if os.path.exists(DEFAULT_TOKEN_FILE):
        with open(DEFAULT_TOKEN_FILE, "r", encoding="utf-8") as fh:
            tok = fh.read().strip()
        if tok:
            return tok
    sys.exit(
        "ERROR: no bot token found. Pass --token, set TELEGRAM_BOT_TOKEN, "
        "or create telegram_emoji/token.txt.\n"
        "Use the token of @pindaobianjiqibot (the bot that owns these sets)."
    )


def load_names(path: str) -> List[str]:
    names: List[str] = []
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            # Allow trailing "# note" comments after the name.
            name = line.split("#", 1)[0].strip()
            if name:
                names.append(name)
    # De-dup while preserving order.
    seen = set()
    unique = []
    for n in names:
        if n not in seen:
            seen.add(n)
            unique.append(n)
    return unique


def call_api(token: str, method: str, params: dict, timeout: int = 30) -> dict:
    """Call a Bot API method; return the parsed JSON response (ok/result/...)."""
    url = f"{API_BASE}/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"ok": False, "error_code": exc.code, "description": body[:300]}


def set_title(token: str, name: str, title: str, max_retries: int = 4) -> tuple:
    """Return (ok: bool, message: str). Handles 429 rate-limits with backoff."""
    delay = 2.0
    for attempt in range(1, max_retries + 1):
        try:
            res = call_api(token, "setStickerSetTitle",
                           {"name": name, "title": title})
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == max_retries:
                return False, f"network error: {exc}"
            time.sleep(delay)
            delay *= 2
            continue

        if res.get("ok"):
            return True, "ok"

        desc = res.get("description", "unknown error")
        # Respect Telegram's flood-wait.
        retry_after = (res.get("parameters") or {}).get("retry_after")
        if res.get("error_code") == 429 and retry_after and attempt < max_retries:
            wait = float(retry_after) + 1
            print(f"    rate-limited, waiting {wait:.0f}s ...", flush=True)
            time.sleep(wait)
            continue
        if res.get("error_code") in (500, 502, 503, 504) and attempt < max_retries:
            time.sleep(delay)
            delay *= 2
            continue
        return False, desc
    return False, "exhausted retries"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--token", help="bot token (default: env TELEGRAM_BOT_TOKEN "
                                    "or telegram_emoji/token.txt)")
    ap.add_argument("--title", default=DEFAULT_TITLE,
                    help=f"new title for every set (default: {DEFAULT_TITLE!r})")
    ap.add_argument("--names-file", default=DEFAULT_NAMES_FILE,
                    help="file listing sticker-set names (default: sets.txt)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would happen, make no network calls")
    ap.add_argument("--sleep", type=float, default=0.5,
                    help="seconds to wait between sets (default: 0.5)")
    args = ap.parse_args()

    title = args.title.strip()
    if not (1 <= len(title) <= MAX_TITLE_LEN):
        sys.exit(f"ERROR: title must be 1-{MAX_TITLE_LEN} chars (got {len(title)}).")

    names = load_names(args.names_file)
    if not names:
        sys.exit(f"ERROR: no sticker-set names found in {args.names_file}")

    print(f"Sets to rename : {len(names)}")
    print(f"New title      : {title!r}")
    print(f"Names file     : {args.names_file}")
    if args.dry_run:
        print("Mode           : DRY RUN (no network calls)\n")
        for i, name in enumerate(names, 1):
            print(f"  [{i:>2}/{len(names)}] would set title of {name} -> {title!r}")
        print("\nDry run complete. Re-run without --dry-run to apply.")
        return 0

    token = load_token(args.token)
    print("Mode           : LIVE\n")

    ok_count = 0
    failures = []
    for i, name in enumerate(names, 1):
        ok, msg = set_title(token, name, title)
        status = "OK " if ok else "FAIL"
        print(f"  [{i:>2}/{len(names)}] {status} {name}"
              + ("" if ok else f"  -> {msg}"), flush=True)
        if ok:
            ok_count += 1
        else:
            failures.append((name, msg))
        if i < len(names):
            time.sleep(args.sleep)

    print(f"\nDone. {ok_count}/{len(names)} succeeded.")
    if failures:
        print("Failed sets:")
        for name, msg in failures:
            print(f"  - {name}: {msg}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
