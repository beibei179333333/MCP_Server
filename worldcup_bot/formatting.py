"""Turn Match objects into nicely formatted Telegram (HTML) messages."""
from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from .flags import flag
from .i18n import canonical_stage, stage_name, t
from .models import Match


def _tz(name: str):
    if ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone.utc


def fmt_time(dt: Optional[datetime], tzname: str, lang: str = "zh") -> str:
    if dt is None:
        return "TBD"
    local = dt.astimezone(_tz(tzname))
    if lang == "zh":
        return local.strftime("%m月%d日 %H:%M")
    return local.strftime("%b %d %H:%M")


def _e(text: str) -> str:
    return html.escape(text or "")


def teams_line(m: Match) -> str:
    return f"{flag(m.home)} {_e(m.home)} vs {_e(m.away)} {flag(m.away)}"


def score_line(m: Match) -> str:
    return f"{flag(m.home)} {_e(m.home)} <b>{m.home_score}-{m.away_score}</b> {_e(m.away)} {flag(m.away)}"


def match_line(m: Match, tzname: str, lang: str = "zh") -> str:
    """A single compact line for list views."""
    stage = stage_name(m.stage, lang)
    grp = ""
    if m.group:
        grp = " · " + m.group.replace("_", " ").title()
    meta = f" <i>({stage}{grp})</i>" if stage else ""
    if m.is_live:
        minute = f" ⏱{m.minute}'" if m.minute else ""
        tag = "🔴" if m.status == "IN_PLAY" else "⏸️"
        return f"{tag} {score_line(m)}{minute}{meta}"
    if m.is_finished and m.has_score:
        return f"✅ {score_line(m)}{meta}"
    return f"🕒 {fmt_time(m.utc_date, tzname, lang)}  {teams_line(m)}{meta}"


def match_list(title: str, matches: list[Match], tzname: str, lang: str = "zh",
               empty: str = "") -> str:
    if not matches:
        return empty or title
    lines = [title, ""]
    lines += [match_line(m, tzname, lang) for m in matches]
    return "\n".join(lines)


def schedule_line(m: Match, tzname: str, lang: str = "zh") -> str:
    """One fixture line for the schedule view (time · teams · venue/result)."""
    when = fmt_time(m.utc_date, tzname, lang)
    if m.is_finished and m.has_score:
        body = score_line(m) + ("  ✅")
    elif m.is_live:
        minute = f" ⏱{m.minute}'" if m.minute else ""
        body = score_line(m) + f"  🔴{minute}"
    else:
        body = teams_line(m)
    venue = f"  📍{_e(m.venue)}" if m.venue else ""
    grp = ""
    if m.group:
        grp = " · " + m.group.replace("_", " ").title()
    return f"🕒 {when}{grp}\n   {body}{venue}"


def stage_schedule(matches: list[Match], stage_code: str, tzname: str,
                   lang: str = "zh") -> list[str]:
    """All fixtures of one stage, sorted by date, returned as message chunks
    (each < ~3500 chars to stay under Telegram's 4096 limit)."""
    target = canonical_stage(stage_code)
    sel = [m for m in matches if canonical_stage(m.stage) == target]
    sel.sort(key=lambda m: (m.utc_date or datetime.max.replace(tzinfo=timezone.utc),
                            m.group or ""))
    title = f"{stage_name(stage_code, lang)}"
    if not sel:
        return [f"<b>{title}</b>\n\n" + t("sched_stage_empty", lang)]

    header = f"<b>{title}</b> · {len(sel)} 场\n"
    chunks: list[str] = []
    buf = [header]
    size = len(header)
    for m in sel:
        line = schedule_line(m, tzname, lang) + "\n"
        if size + len(line) > 3500:
            chunks.append("".join(buf))
            buf = [header]
            size = len(header)
        buf.append(line)
        size += len(line)
    chunks.append("".join(buf))
    return chunks


def standings_block(groups: list[dict], lang: str = "zh") -> str:
    head = t("standings_title", lang)
    out = [head]
    for g in groups:
        out.append(f"\n<b>{_e(g['group'])}</b>")
        out.append("<pre>#  队伍            积 胜平负 净")
        for r in g["table"]:
            name = (r["team"] or "")[:14].ljust(14)
            pos = str(r.get("position", "")).rjust(2)
            pts = str(r.get("points", "")).rjust(2)
            w = r.get("won", 0); d = r.get("draw", 0); l = r.get("lost", 0)
            gd = r.get("gd", 0)
            gd_s = (f"+{gd}" if gd > 0 else str(gd)).rjust(3)
            out.append(f"{pos} {name} {pts} {w}{d}{l} {gd_s}")
        out.append("</pre>")
    return "\n".join(out)


# ---- live event messages -----------------------------------------------
def event_reminder(m: Match, tzname: str, minutes: int, lang: str = "zh") -> str:
    if lang == "zh":
        return (f"⏰ <b>开赛提醒</b>（约 {minutes} 分钟后）\n"
                f"{teams_line(m)}\n🕒 {fmt_time(m.utc_date, tzname, lang)}"
                f"  <i>{stage_name(m.stage, lang)}</i>")
    return (f"⏰ <b>Kickoff in ~{minutes} min</b>\n{teams_line(m)}\n"
            f"🕒 {fmt_time(m.utc_date, tzname, lang)}  <i>{stage_name(m.stage, lang)}</i>")


def event_kickoff(m: Match, lang: str = "zh") -> str:
    if lang == "zh":
        return f"🟢 <b>开球！</b>\n{teams_line(m)}\n<i>{stage_name(m.stage, lang)}</i>"
    return f"🟢 <b>Kickoff!</b>\n{teams_line(m)}\n<i>{stage_name(m.stage, lang)}</i>"


def event_goal(m: Match, scorer_side: str, lang: str = "zh") -> str:
    who = m.home if scorer_side == "home" else m.away
    if lang == "zh":
        return (f"⚽️ <b>进球！</b> {flag(who)} {_e(who)}\n{score_line(m)}"
                + (f"  ⏱{m.minute}'" if m.minute else ""))
    return (f"⚽️ <b>GOAL!</b> {flag(who)} {_e(who)}\n{score_line(m)}"
            + (f"  ⏱{m.minute}'" if m.minute else ""))


def event_halftime(m: Match, lang: str = "zh") -> str:
    if lang == "zh":
        return f"⏸️ <b>半场结束</b>\n{score_line(m)}"
    return f"⏸️ <b>Half-time</b>\n{score_line(m)}"


def event_fulltime(m: Match, lang: str = "zh") -> str:
    if m.winner == "DRAW" or (m.has_score and m.home_score == m.away_score):
        result = "平局" if lang == "zh" else "Draw"
    else:
        win = m.home if (m.has_score and m.home_score > m.away_score) else m.away
        result = (f"{flag(win)} {win} 获胜" if lang == "zh" else f"{flag(win)} {win} win")
    head = "🏁 <b>终场</b>" if lang == "zh" else "🏁 <b>Full-time</b>"
    return f"{head}\n{score_line(m)}\n{_e(result)}  <i>{stage_name(m.stage, lang)}</i>"
