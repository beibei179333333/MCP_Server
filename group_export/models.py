"""Normalized member model and field mapping from arbitrary API payloads."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, Optional


# Candidate source-field names mapped to our canonical fields. The bot API may
# use any of these; we probe them in order and take the first non-empty value.
_FIELD_ALIASES: Dict[str, tuple] = {
    "user_id": ("user_id", "userId", "id", "uid", "tg_id", "tgId", "telegram_id"),
    "username": ("username", "user_name", "userName", "login", "handle", "nick"),
    "first_name": ("first_name", "firstName", "first", "fname"),
    "last_name": ("last_name", "lastName", "last", "lname"),
    "full_name": ("full_name", "fullName", "name", "display_name", "displayName", "title"),
    "phone": ("phone", "phone_number", "phoneNumber", "mobile"),
    "bio": ("bio", "about", "description", "status", "signature"),
    "is_bot": ("is_bot", "isBot", "bot"),
    "is_premium": ("is_premium", "isPremium", "premium"),
    "is_verified": ("is_verified", "isVerified", "verified"),
    "is_scam": ("is_scam", "isScam", "scam"),
    "is_fake": ("is_fake", "isFake", "fake"),
    "language_code": ("language_code", "languageCode", "lang", "language"),
    "join_date": ("join_date", "joinDate", "joined_at", "joinedAt", "join_time", "joinTime"),
    "last_seen": ("last_seen", "lastSeen", "last_online", "lastOnline", "last_active"),
    "message_count": ("message_count", "messageCount", "messages", "msg_count", "msgCount"),
    "has_photo": ("has_photo", "hasPhoto", "photo", "avatar", "has_avatar", "profile_photo", "photo_url"),
}


def _to_photo(v: Any):
    """Tri-state: True / False / None (unknown — field not provided)."""
    if v in (None, ""):
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    s = str(v).strip().lower()
    if s in ("0", "false", "no", "none", "null"):
        return False
    return True


def _first(d: Dict[str, Any], keys: Iterable[str]) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, "", []):
            return d[k]
    return None


def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "y", "t")
    return False


def _clean_username(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if s.startswith("@"):
        s = s[1:]
    return s


@dataclass
class Member:
    user_id: str = ""
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    full_name: str = ""
    phone: str = ""
    bio: str = ""
    is_bot: bool = False
    is_premium: bool = False
    is_verified: bool = False
    is_scam: bool = False
    is_fake: bool = False
    language_code: str = ""
    join_date: str = ""
    last_seen: str = ""
    message_count: int = 0
    has_photo: Optional[bool] = None
    # Bookkeeping: which group(s) this member was seen in.
    groups: set = field(default_factory=set)
    # Original raw record(s), kept for debugging / re-export.
    raw: list = field(default_factory=list)

    @classmethod
    def from_raw(cls, rec: Dict[str, Any], group: Optional[str] = None) -> "Member":
        if not isinstance(rec, dict):
            rec = {"value": rec}
        vals: Dict[str, Any] = {}
        for canon, aliases in _FIELD_ALIASES.items():
            vals[canon] = _first(rec, aliases)

        first = (vals.get("first_name") or "").strip() if vals.get("first_name") else ""
        last = (vals.get("last_name") or "").strip() if vals.get("last_name") else ""
        full = (vals.get("full_name") or "").strip() if vals.get("full_name") else ""
        if not full:
            full = " ".join(p for p in (first, last) if p).strip()

        try:
            mc = int(vals.get("message_count") or 0)
        except (TypeError, ValueError):
            mc = 0

        m = cls(
            user_id=str(vals.get("user_id") or "").strip(),
            username=_clean_username(vals.get("username")),
            first_name=first,
            last_name=last,
            full_name=full,
            phone=str(vals.get("phone") or "").strip(),
            bio=str(vals.get("bio") or "").strip(),
            is_bot=_to_bool(vals.get("is_bot")),
            is_premium=_to_bool(vals.get("is_premium")),
            is_verified=_to_bool(vals.get("is_verified")),
            is_scam=_to_bool(vals.get("is_scam")),
            is_fake=_to_bool(vals.get("is_fake")),
            language_code=str(vals.get("language_code") or "").strip(),
            join_date=str(vals.get("join_date") or "").strip(),
            last_seen=str(vals.get("last_seen") or "").strip(),
            message_count=mc,
            has_photo=_to_photo(vals.get("has_photo")),
        )
        if group:
            m.groups.add(str(group))
        m.raw.append(rec)
        return m

    @property
    def dedup_key(self) -> str:
        """Stable identity for dedup: prefer user_id, else @username."""
        if self.user_id:
            return f"id:{self.user_id}"
        if self.username:
            return f"un:{self.username.lower()}"
        return f"nm:{self.full_name.lower()}"

    def merge(self, other: "Member") -> None:
        """Fold another record for the same identity into this one, keeping the
        most complete / most recent information."""
        for attr in (
            "user_id", "username", "first_name", "last_name", "full_name",
            "phone", "bio", "language_code", "join_date", "last_seen",
        ):
            if not getattr(self, attr) and getattr(other, attr):
                setattr(self, attr, getattr(other, attr))
        for attr in ("is_bot", "is_premium", "is_verified", "is_scam", "is_fake"):
            setattr(self, attr, getattr(self, attr) or getattr(other, attr))
        if self.has_photo is None:
            self.has_photo = other.has_photo
        elif other.has_photo is True:
            self.has_photo = True
        self.message_count = max(self.message_count, other.message_count)
        self.groups |= other.groups
        self.raw.extend(other.raw)

    def to_row(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("raw", None)
        d["groups"] = ",".join(sorted(self.groups))
        d["has_photo"] = "" if self.has_photo is None else ("是" if self.has_photo else "否")
        return d


EXPORT_COLUMNS = [
    "user_id", "username", "full_name", "first_name", "last_name",
    "phone", "is_bot", "is_premium", "is_verified", "is_scam", "is_fake",
    "has_photo", "language_code", "message_count", "join_date", "last_seen",
    "bio", "groups",
]
