"""Country -> flag emoji map for World Cup nations (best-effort, ⚽ fallback)."""
from __future__ import annotations

# Keys are matched case-insensitively against the team name. We keep both the
# common English names and a few alternates that data feeds sometimes use.
_FLAGS = {
    "qatar": "🇶🇦", "ecuador": "🇪🇨", "senegal": "🇸🇳", "netherlands": "🇳🇱",
    "england": "🏴\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f",
    "iran": "🇮🇷", "ir iran": "🇮🇷", "united states": "🇺🇸", "usa": "🇺🇸",
    "wales": "🏴\U000e0067\U000e0062\U000e0077\U000e006c\U000e0073\U000e007f",
    "argentina": "🇦🇷", "saudi arabia": "🇸🇦", "mexico": "🇲🇽", "poland": "🇵🇱",
    "france": "🇫🇷", "australia": "🇦🇺", "denmark": "🇩🇰", "tunisia": "🇹🇳",
    "spain": "🇪🇸", "costa rica": "🇨🇷", "germany": "🇩🇪", "japan": "🇯🇵",
    "belgium": "🇧🇪", "canada": "🇨🇦", "morocco": "🇲🇦", "croatia": "🇭🇷",
    "brazil": "🇧🇷", "serbia": "🇷🇸", "switzerland": "🇨🇭", "cameroon": "🇨🇲",
    "portugal": "🇵🇹", "ghana": "🇬🇭", "uruguay": "🇺🇾", "south korea": "🇰🇷",
    "korea republic": "🇰🇷", "republic of korea": "🇰🇷",
    "italy": "🇮🇹", "colombia": "🇨🇴", "nigeria": "🇳🇬", "egypt": "🇪🇬",
    "algeria": "🇩🇿", "chile": "🇨🇱", "peru": "🇵🇪", "ivory coast": "🇨🇮",
    "côte d'ivoire": "🇨🇮", "cote d'ivoire": "🇨🇮", "sweden": "🇸🇪",
    "norway": "🇳🇴", "austria": "🇦🇹", "ukraine": "🇺🇦", "scotland":
    "🏴\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f",
    "turkey": "🇹🇷", "türkiye": "🇹🇷", "greece": "🇬🇷", "russia": "🇷🇺",
    "paraguay": "🇵🇾", "venezuela": "🇻🇪", "panama": "🇵🇦", "jamaica": "🇯🇲",
    "honduras": "🇭🇳", "south africa": "🇿🇦", "mali": "🇲🇱", "burkina faso": "🇧🇫",
    "dr congo": "🇨🇩", "congo dr": "🇨🇩", "new zealand": "🇳🇿", "jordan": "🇯🇴",
    "uzbekistan": "🇺🇿", "iraq": "🇮🇶", "qatar ": "🇶🇦", "cape verde": "🇨🇻",
    "cabo verde": "🇨🇻", "haiti": "🇭🇹", "curaçao": "🇨🇼", "curacao": "🇨🇼",
    "bolivia": "🇧🇴", "indonesia": "🇮🇩", "united arab emirates": "🇦🇪",
    "uae": "🇦🇪", "guinea": "🇬🇳", "slovenia": "🇸🇮", "slovakia": "🇸🇰",
    "czechia": "🇨🇿", "czech republic": "🇨🇿", "romania": "🇷🇴", "hungary": "🇭🇺",
    "georgia": "🇬🇪", "albania": "🇦🇱", "wales ": "🏴",
}


def flag(team_name: str) -> str:
    if not team_name:
        return "⚽"
    return _FLAGS.get(team_name.strip().lower(), "⚽")
