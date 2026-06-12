"""Tiny bilingual (zh / en) string table for user-facing text."""
from __future__ import annotations

STR = {
    "welcome": {
        "zh": (
            "⚽️ <b>2026 世界杯实时通知机器人</b>\n\n"
            "你已订阅！开赛提醒、进球、半场、终场比分都会第一时间推送给你。\n\n"
            "常用命令：\n"
            "/today 今日赛程\n"
            "/live 正在进行的比赛\n"
            "/next 接下来的比赛\n"
            "/matches 全部赛程\n"
            "/standings 小组积分榜\n"
            "/settings 通知设置\n"
            "/lang 中文 / English\n"
            "/unsubscribe 取消订阅\n"
            "/help 帮助"
        ),
        "en": (
            "⚽️ <b>2026 World Cup Live Notifier</b>\n\n"
            "You're subscribed! You'll get kickoff reminders, goals, "
            "half-time and full-time results in real time.\n\n"
            "Commands:\n"
            "/today  Today's fixtures\n"
            "/live   Matches in play\n"
            "/next   Upcoming matches\n"
            "/matches  Full schedule\n"
            "/standings  Group tables\n"
            "/settings  Notification settings\n"
            "/lang  中文 / English\n"
            "/unsubscribe  Stop notifications\n"
            "/help  Help"
        ),
    },
    "help": {
        "zh": (
            "📖 <b>使用说明</b>\n\n"
            "/start 订阅并查看命令\n"
            "/today 今天的比赛\n"
            "/live 正在踢的比赛\n"
            "/next 接下来 5 场\n"
            "/matches 全部赛程\n"
            "/standings 小组积分榜\n"
            "/settings 开关各类通知（开赛提醒/进球/半场/终场）\n"
            "/lang 切换语言\n"
            "/subscribe 重新订阅\n"
            "/unsubscribe 取消订阅\n"
            "/whoami 查看本会话 ID"
        ),
        "en": (
            "📖 <b>Help</b>\n\n"
            "/start subscribe & show commands\n"
            "/today today's matches\n"
            "/live matches in play\n"
            "/next next 5 matches\n"
            "/matches full schedule\n"
            "/standings group tables\n"
            "/settings toggle notifications\n"
            "/lang switch language\n"
            "/subscribe re-subscribe\n"
            "/unsubscribe stop notifications\n"
            "/whoami show this chat id"
        ),
    },
    "subscribed": {"zh": "✅ 订阅成功，赛事通知已开启。", "en": "✅ Subscribed. Live notifications are on."},
    "unsubscribed": {"zh": "👋 已取消订阅，随时 /subscribe 回来。", "en": "👋 Unsubscribed. /subscribe anytime."},
    "already_sub": {"zh": "你已经订阅过啦 ✅", "en": "You're already subscribed ✅"},
    "not_sub": {"zh": "你还没有订阅，发送 /start 开始。", "en": "You're not subscribed. Send /start."},
    "no_today": {"zh": "今天没有安排比赛 🗓️", "en": "No matches scheduled today 🗓️"},
    "no_live": {"zh": "现在没有正在进行的比赛 😴", "en": "No matches in play right now 😴"},
    "no_next": {"zh": "暂时没有接下来的比赛。", "en": "No upcoming matches."},
    "no_matches": {"zh": "暂时拿不到赛程数据。", "en": "No schedule data available."},
    "today_title": {"zh": "🗓️ <b>今日赛程</b>", "en": "🗓️ <b>Today's fixtures</b>"},
    "live_title": {"zh": "🔴 <b>正在进行</b>", "en": "🔴 <b>Live now</b>"},
    "next_title": {"zh": "⏭️ <b>接下来的比赛</b>", "en": "⏭️ <b>Upcoming</b>"},
    "matches_title": {"zh": "📋 <b>全部赛程</b>", "en": "📋 <b>Full schedule</b>"},
    "standings_title": {"zh": "📊 <b>小组积分榜</b>", "en": "📊 <b>Group standings</b>"},
    "standings_na": {"zh": "积分榜暂不可用。", "en": "Standings not available."},
    "settings_title": {"zh": "⚙️ <b>通知设置</b>（点击开关）", "en": "⚙️ <b>Notification settings</b> (tap to toggle)"},
    "lang_set": {"zh": "✅ 已切换为中文。", "en": "✅ Switched to English."},
    "lang_choose": {"zh": "选择语言 / Choose language：", "en": "Choose language / 选择语言："},
    "reminder": {"zh": "开赛提醒", "en": "Kickoff reminder"},
    "kickoff": {"zh": "开赛", "en": "Kickoff"},
    "goals": {"zh": "进球", "en": "Goals"},
    "halftime": {"zh": "半场", "en": "Half-time"},
    "fulltime": {"zh": "终场", "en": "Full-time"},
    "on": {"zh": "开", "en": "ON"},
    "off": {"zh": "关", "en": "OFF"},
    "whoami": {"zh": "本会话 chat id：<code>{cid}</code>", "en": "This chat id: <code>{cid}</code>"},
    "unknown_cmd": {"zh": "未知命令，发送 /help 查看用法。", "en": "Unknown command. Send /help."},
    "demo_note": {
        "zh": "ℹ️ 当前为 <b>演示模式</b>（无 API Key）：比赛数据为模拟生成，用于体验通知效果。",
        "en": "ℹ️ <b>Demo mode</b> (no API key): match data is simulated to showcase notifications.",
    },
}

STAGE = {
    "GROUP_STAGE": {"zh": "小组赛", "en": "Group stage"},
    "LAST_16": {"zh": "1/8 决赛", "en": "Round of 16"},
    "ROUND_OF_16": {"zh": "1/8 决赛", "en": "Round of 16"},
    "QUARTER_FINALS": {"zh": "1/4 决赛", "en": "Quarter-finals"},
    "SEMI_FINALS": {"zh": "半决赛", "en": "Semi-finals"},
    "THIRD_PLACE": {"zh": "三四名决赛", "en": "Third place"},
    "FINAL": {"zh": "决赛", "en": "Final"},
}


def t(key: str, lang: str = "zh", **kw) -> str:
    entry = STR.get(key, {})
    text = entry.get(lang) or entry.get("zh") or key
    return text.format(**kw) if kw else text


def stage_name(stage: str, lang: str = "zh") -> str:
    entry = STAGE.get((stage or "").upper())
    if not entry:
        return stage.replace("_", " ").title() if stage else ""
    return entry.get(lang, entry.get("zh", stage))
