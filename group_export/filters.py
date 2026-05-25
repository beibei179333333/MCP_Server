"""Heuristic filters: no-username and ad/marketing-account detection."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from .models import Member


# Keywords that strongly indicate an advertising / marketing / spam account.
# Mix of zh-CN and English terms common in Telegram marketing spam.
DEFAULT_AD_KEYWORDS: List[str] = [
    # zh-CN marketing / ads
    "广告", "推广", "营销", "引流", "招商", "代理", "代充", "承接", "出售", "出粉",
    "卖", "购买", "招聘", "兼职", "刷单", "刷量", "粉丝", "拉人", "拉群", "建群",
    "加微", "加我", "私聊", "联系", "客服", "在线", "咨询", "办理", "接单", "接业务",
    "博彩", "菠菜", "彩票", "棋牌", "赌", "色情", "约炮", "约", "贷款", "网赚", "赚钱",
    "USDT", "usdt", "U商", "承兑", "跑分", "支付", "通道", "三方", "四方",
    "飞机号", "tg号", "TG号", "协议号", "白号", "老号", "实名", "解封", "群发",
    "机器人", "脚本", "软件", "破解", "VPN", "翻墙", "节点", "梯子",
    # English / generic spam
    "promo", "promotion", "marketing", "advertis", "casino", "betting", "loan",
    "crypto", "forex", "invest", "earn money", "make money", "free money",
    "click here", "join now", "subscribe", "follow me", "dm me", "contact me",
    "for sale", "cheap", "discount", "telegram.me", "t.me/", "wa.me",
    "official", "support team", "admin", "airdrop", "giveaway", "presale",
]

# Patterns that look promotional inside a display name or bio.
_URL_RE = re.compile(r"(https?://|t\.me/|telegram\.me/|wa\.me/|@[A-Za-z0-9_]{4,})", re.I)
_PHONE_RE = re.compile(r"(?:\+?\d[\s\-]?){9,}")
# Run of emoji / pictographs (decorated marketing names).
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF←-⇿⬀-⯿]"
)


@dataclass
class FilterConfig:
    require_username: bool = True
    filter_ads: bool = True
    filter_bots: bool = True
    filter_scam_fake: bool = True
    ad_keywords: Optional[List[str]] = None
    # Score threshold; a member is flagged as ad when score >= threshold.
    ad_threshold: int = 2
    # Names with at least this many emoji are treated as decorated/marketing.
    emoji_limit: int = 4

    def keywords(self) -> List[str]:
        return [k.lower() for k in (self.ad_keywords or DEFAULT_AD_KEYWORDS)]


def _haystack(m: Member) -> str:
    return " ".join(
        x for x in (m.username, m.full_name, m.first_name, m.last_name, m.bio) if x
    ).lower()


def ad_score(m: Member, cfg: FilterConfig) -> int:
    """Return a heuristic 'looks like an ad/marketing account' score."""
    text = _haystack(m)
    score = 0

    kw_hits = sum(1 for kw in cfg.keywords() if kw and kw in text)
    score += kw_hits

    blob = " ".join(x for x in (m.username, m.full_name, m.bio) if x)
    if _URL_RE.search(blob):
        score += 2
    if _PHONE_RE.search(m.full_name) or _PHONE_RE.search(m.bio):
        score += 2

    emoji_count = len(_EMOJI_RE.findall(m.full_name))
    if emoji_count >= cfg.emoji_limit:
        score += 1

    if m.is_scam or m.is_fake:
        score += 3

    return score


def classify(m: Member, cfg: FilterConfig) -> Optional[str]:
    """Return a reason string if the member should be filtered out, else None."""
    if cfg.require_username and not m.username:
        return "no_username"
    if cfg.filter_bots and m.is_bot:
        return "bot"
    if cfg.filter_scam_fake and (m.is_scam or m.is_fake):
        return "scam_or_fake"
    if cfg.filter_ads and ad_score(m, cfg) >= cfg.ad_threshold:
        return "ad_marketing"
    return None
