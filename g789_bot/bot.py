"""Telegram bot that serves all 500 G789 scenario skills.

Users browse scenarios by category or search, pick one, and then chat with that
scenario's self-contained workflow — backed by Claude. Built on
python-telegram-bot (async, v21+).
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator

import anthropic
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatAction
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Config
from .llm import LLM
from .skills import Catalog, Skill

log = logging.getLogger("g789_bot")

TELEGRAM_LIMIT = 4096
_SAFE_CHUNK = 3900
PAGE_SIZE = 8
CATS_PER_PAGE = 24

# ---------------------------------------------------------------------------
# Keyboards & rendering
# ---------------------------------------------------------------------------


def _main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📂 按类目浏览 / Browse", callback_data="cats:0")],
            [InlineKeyboardButton("🎲 随机一个 / Random", callback_data="rand")],
            [InlineKeyboardButton("❓ 帮助 / Help", callback_data="help")],
        ]
    )


def _categories_keyboard(catalog: Catalog, page: int) -> InlineKeyboardMarkup:
    cats = catalog.categories()
    start = page * CATS_PER_PAGE
    chunk = cats[start : start + CATS_PER_PAGE]
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for name, count in chunk:
        row.append(
            InlineKeyboardButton(f"{name} ({count})", callback_data=f"cat:{name}:0")
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    nav: list[InlineKeyboardButton] = []
    if start > 0:
        nav.append(InlineKeyboardButton("« 上一页", callback_data=f"cats:{page - 1}"))
    if start + CATS_PER_PAGE < len(cats):
        nav.append(InlineKeyboardButton("下一页 »", callback_data=f"cats:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🏠 菜单 / Menu", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def _skills_keyboard(skills: list[Skill], category: str, page: int) -> InlineKeyboardMarkup:
    start = page * PAGE_SIZE
    chunk = skills[start : start + PAGE_SIZE]
    rows = [
        [InlineKeyboardButton(_clip(s.title, 60), callback_data=f"pick:{s.id}")]
        for s in chunk
    ]
    nav: list[InlineKeyboardButton] = []
    if start > 0:
        nav.append(InlineKeyboardButton("« 上一页", callback_data=f"cat:{category}:{page - 1}"))
    if start + PAGE_SIZE < len(skills):
        nav.append(InlineKeyboardButton("下一页 »", callback_data=f"cat:{category}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("📂 类目 / Categories", callback_data="cats:0")])
    return InlineKeyboardMarkup(rows)


def _search_keyboard(results: list[Skill]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(_clip(s.title, 60), callback_data=f"pick:{s.id}")]
        for s in results
    ]
    rows.append([InlineKeyboardButton("🏠 菜单 / Menu", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def _split_message(text: str) -> list[str]:
    """Split text into Telegram-sized pieces, preferring line boundaries."""
    text = text.strip() or "（无内容）"
    parts: list[str] = []
    while len(text) > TELEGRAM_LIMIT:
        cut = text.rfind("\n", 0, _SAFE_CHUNK)
        if cut <= 0:
            cut = _SAFE_CHUNK
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    parts.append(text)
    return parts


# ---------------------------------------------------------------------------
# Per-chat state helpers (stored in PTB's in-memory chat_data)
# ---------------------------------------------------------------------------


def _catalog(context: ContextTypes.DEFAULT_TYPE) -> Catalog:
    return context.application.bot_data["catalog"]


def _llm(context: ContextTypes.DEFAULT_TYPE) -> LLM:
    return context.application.bot_data["llm"]


def _config(context: ContextTypes.DEFAULT_TYPE) -> Config:
    return context.application.bot_data["config"]


def _active_skill(context: ContextTypes.DEFAULT_TYPE) -> Skill | None:
    skill_id = context.chat_data.get("skill_id")
    if not skill_id:
        return None
    return _catalog(context).get(skill_id)


def _activate(context: ContextTypes.DEFAULT_TYPE, skill: Skill) -> None:
    context.chat_data["skill_id"] = skill.id
    context.chat_data["history"] = []


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

WELCOME = (
    "👋 *G789 场景技能机器人*\n\n"
    "这里收录了 {n} 个自包含的场景助手（S-001 … S-500），涵盖生活、工作、文案、"
    "编程、设计、运营等数十个类目。\n\n"
    "用法：\n"
    "• 点下面的按钮按类目浏览，或直接发送关键词 / 场景编号（如 `S-042`）搜索\n"
    "• 选定场景后，直接像聊天一样对话即可\n"
    "• /menu 菜单 · /end 退出当前场景 · /help 帮助\n"
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        WELCOME.format(n=len(_catalog(context))),
        reply_markup=_main_menu(),
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "📖 *帮助*\n\n"
        "• /start 或 /menu — 主菜单\n"
        "• /search <关键词> — 搜索场景（也可直接发送关键词）\n"
        "• /skill <编号> — 直接进入某个场景，如 `/skill S-100`\n"
        "• /random — 随机一个场景\n"
        "• /end — 退出当前场景，回到搜索/浏览\n"
        "• /current — 查看当前所处场景\n\n"
        "选定场景后，直接发消息就会以该场景助手的身份回复你。",
        parse_mode="Markdown",
    )


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "请选择 / Choose:", reply_markup=_main_menu()
    )


async def cmd_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    had = context.chat_data.pop("skill_id", None)
    context.chat_data.pop("history", None)
    msg = "已退出当前场景。" if had else "当前没有进行中的场景。"
    await update.effective_message.reply_text(
        msg + " 发送关键词搜索，或 /menu 浏览。"
    )


async def cmd_current(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    skill = _active_skill(context)
    if skill is None:
        await update.effective_message.reply_text("当前没有进行中的场景。/menu 浏览。")
    else:
        await update.effective_message.reply_text(
            f"当前场景：*{skill.title}*（类目：{skill.category}）\n/end 可退出。",
            parse_mode="Markdown",
        )


async def cmd_random(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import random

    skill = random.choice(_catalog(context).skills)
    _activate(context, skill)
    await _announce_skill(update.effective_message.reply_text, skill)


async def cmd_skill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("用法：/skill S-042")
        return
    skill = _catalog(context).get(context.args[0])
    if skill is None:
        await update.effective_message.reply_text("没找到这个编号。试试 /search 或 /menu。")
        return
    _activate(context, skill)
    await _announce_skill(update.effective_message.reply_text, skill)


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = " ".join(context.args).strip()
    if not query:
        await update.effective_message.reply_text("用法：/search 关键词")
        return
    await _do_search(update, context, query)


# ---------------------------------------------------------------------------
# Free-text handler: chat if a scenario is active, otherwise search
# ---------------------------------------------------------------------------


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.effective_message.text or "").strip()
    if not text:
        return
    skill = _active_skill(context)
    if skill is None:
        await _do_search(update, context, text)
    else:
        await _chat(update, context, skill, text)


async def _do_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> None:
    results = _catalog(context).search(query)
    if not results:
        await update.effective_message.reply_text(
            "没有匹配的场景。换个关键词，或 /menu 按类目浏览。"
        )
        return
    head = "🔎 找到这些场景，点一个进入：" if len(results) > 1 else "找到一个场景："
    await update.effective_message.reply_text(head, reply_markup=_search_keyboard(results))


async def _announce_skill(reply, skill: Skill) -> None:
    await reply(
        f"✅ 已进入场景 *{skill.title}*\n类目：{skill.category}\n\n"
        "直接发消息开始对话；/end 退出。",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Callback (inline button) handler
# ---------------------------------------------------------------------------


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data or ""
    await query.answer()
    catalog = _catalog(context)

    if data == "menu":
        await query.edit_message_text("请选择 / Choose:", reply_markup=_main_menu())
    elif data == "help":
        await query.edit_message_text(
            "发送关键词或场景编号（如 S-100）即可搜索；选定后直接对话。\n/help 查看完整帮助。",
            reply_markup=_main_menu(),
        )
    elif data == "rand":
        import random

        skill = random.choice(catalog.skills)
        _activate(context, skill)
        await _announce_skill(query.message.reply_text, skill)
    elif data.startswith("cats:"):
        page = int(data.split(":", 1)[1])
        await query.edit_message_text(
            "📂 选择类目 / Pick a category:",
            reply_markup=_categories_keyboard(catalog, page),
        )
    elif data.startswith("cat:"):
        _, category, page_s = data.split(":", 2)
        skills = catalog.in_category(category)
        await query.edit_message_text(
            f"类目「{category}」共 {len(skills)} 个场景：",
            reply_markup=_skills_keyboard(skills, category, int(page_s)),
        )
    elif data.startswith("pick:"):
        skill = catalog.get(data.split(":", 1)[1])
        if skill is None:
            await query.edit_message_text("场景不存在了，请 /menu 重试。")
            return
        _activate(context, skill)
        await query.edit_message_text(
            f"✅ 已进入场景 *{skill.title}*\n类目：{skill.category}\n\n"
            "直接发消息开始对话；/end 退出。",
            parse_mode="Markdown",
        )


# ---------------------------------------------------------------------------
# Streaming a Claude reply into a Telegram message
# ---------------------------------------------------------------------------


async def _chat(
    update: Update, context: ContextTypes.DEFAULT_TYPE, skill: Skill, text: str
) -> None:
    config = _config(context)
    history: list[dict] = context.chat_data.setdefault("history", [])
    history.append({"role": "user", "content": text})

    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
    placeholder = await update.effective_message.reply_text("…")

    try:
        reply = await _stream_into(
            context, chat_id, placeholder.message_id,
            _llm(context).stream_reply(skill, _trim(history, config.max_history_turns)),
        )
    except anthropic.APIStatusError as exc:
        log.warning("Anthropic API error: %s", exc)
        history.pop()  # don't poison history with a failed turn
        await _safe_edit(context, chat_id, placeholder.message_id,
                         "⚠️ 模型调用出错了，请稍后再试。")
        return
    except Exception:  # noqa: BLE001 — surface a friendly message, keep the bot alive
        log.exception("Unexpected error while streaming reply")
        history.pop()
        await _safe_edit(context, chat_id, placeholder.message_id,
                         "⚠️ 出错了，请稍后再试。")
        return

    history.append({"role": "assistant", "content": reply})
    context.chat_data["history"] = _trim(history, config.max_history_turns)


async def _stream_into(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    chunks: AsyncIterator[str],
) -> str:
    """Edit ``message_id`` as text streams in; spill into new messages if huge."""
    buffer = ""
    last_len = 0
    last_edit = 0.0
    async for chunk in chunks:
        buffer += chunk
        now = time.monotonic()
        if len(buffer) <= _SAFE_CHUNK and len(buffer) != last_len and (now - last_edit) > 1.1:
            await _safe_edit(context, chat_id, message_id, buffer + " ▌")
            last_len = len(buffer)
            last_edit = now

    pieces = _split_message(buffer)
    await _safe_edit(context, chat_id, message_id, pieces[0])
    for extra in pieces[1:]:
        await context.bot.send_message(chat_id, extra)
    return buffer.strip()


async def _safe_edit(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, text: str
) -> None:
    try:
        await context.bot.edit_message_text(
            text[:TELEGRAM_LIMIT], chat_id=chat_id, message_id=message_id
        )
    except BadRequest as exc:
        # "message is not modified" and transient edit races are non-fatal.
        if "not modified" not in str(exc).lower():
            log.debug("edit failed: %s", exc)


def _trim(history: list[dict], max_turns: int) -> list[dict]:
    if len(history) <= max_turns:
        return history
    trimmed = history[-max_turns:]
    # The Messages API requires the first message to be from the user.
    while trimmed and trimmed[0]["role"] != "user":
        trimmed = trimmed[1:]
    return trimmed


# ---------------------------------------------------------------------------
# Application wiring
# ---------------------------------------------------------------------------


def build_application(config: Config) -> Application:
    catalog = Catalog(blocked_categories=set(config.blocked_categories))
    if len(catalog) == 0:
        raise RuntimeError("No skills found under g789_bot/skills — nothing to serve.")

    app = ApplicationBuilder().token(config.telegram_token).build()
    app.bot_data["config"] = config
    app.bot_data["catalog"] = catalog
    app.bot_data["llm"] = LLM(config)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("end", cmd_end))
    app.add_handler(CommandHandler("current", cmd_current))
    app.add_handler(CommandHandler("random", cmd_random))
    app.add_handler(CommandHandler("skill", cmd_skill))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app
