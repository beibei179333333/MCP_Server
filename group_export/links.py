"""Parse Telegram group links / handles into a group identifier.

Accepts things like:
  https://t.me/somegroup          -> somegroup
  https://t.me/somegroup/123      -> somegroup
  t.me/+AbCdEf123                 -> +AbCdEf123        (invite hash)
  https://t.me/joinchat/AbCdEf    -> joinchat/AbCdEf
  @somegroup                      -> somegroup
  -1001234567890                  -> -1001234567890    (numeric chat id)
  somegroup                       -> somegroup
"""
from __future__ import annotations

import re
from typing import List, Tuple

_SCHEME_RE = re.compile(r"^[a-z]+://", re.I)


def parse_group_link(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    # strip surrounding quotes / commas / list bullets
    s = s.strip().strip(",;|\"' \t")
    if not s:
        return ""

    # plain numeric chat id (possibly -100...)
    if re.fullmatch(r"-?\d{5,}", s):
        return s

    # @handle
    if s.startswith("@"):
        return s[1:].strip("/")

    # strip scheme
    body = _SCHEME_RE.sub("", s)
    # strip leading www.
    body = re.sub(r"^www\.", "", body, flags=re.I)

    # t.me / telegram.me / telegram.dog hosts
    m = re.match(r"^(?:t\.me|telegram\.me|telegram\.dog)/(.+)$", body, re.I)
    if m:
        path = m.group(1).strip("/")
        # invite links keep their distinguishing part
        if path.startswith("+"):
            return path                      # +hash private invite
        if path.lower().startswith("joinchat/"):
            return path                      # joinchat/<hash>
        # public group: first path segment is the username
        return path.split("/")[0].split("?")[0]

    # not a t.me url: accept only if the first segment looks like a real
    # telegram handle / invite hash; otherwise treat as unrecognized.
    head = body.split("/")[0].split("?")[0]
    if head.startswith("+") and re.fullmatch(r"\+[A-Za-z0-9_-]{4,}", head):
        return head
    if re.fullmatch(r"[A-Za-z0-9_]{4,32}", head):
        return head

    return ""


def parse_many(text: str) -> Tuple[List[str], List[str]]:
    """Split a blob (newlines/commas/spaces) into (unique_groups, skipped_raw)."""
    parts = re.split(r"[\n\r,]+", text or "")
    groups: List[str] = []
    seen = set()
    skipped: List[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        g = parse_group_link(p)
        if not g:
            skipped.append(p)
            continue
        key = g.lower()
        if key in seen:
            continue
        seen.add(key)
        groups.append(g)
    return groups, skipped
