"""搬运规则的 CRUD（执行端在 userbot.py）。"""
from __future__ import annotations

import logging

from sqlalchemy import select
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ..database import ForwardRule, SessionLocal
from ..keyboards import back_home
from ..utils import admin_only

log = logging.getLogger(__name__)

PANEL = """\
📡 *搬运规则管理*

命令：
• `/fw_add 源 目标 [规则名]`
• `/fw_list` — 列出全部规则
• `/fw_del <id>` — 删除
• `/fw_toggle <id>` — 启用 / 停用
• `/fw_filter <id> keywords=a,b | blacklist=c,d`
• `/fw_replace <id> 原文 => 新文`

源 / 目标可以是：
  `@channelname`、`@groupname`、或数字 `-1001234567890`

⚠️ 需要在 .env 配置 `TG_API_ID` `TG_API_HASH` `TG_PHONE`
并首次运行时完成 user-bot 登录。
"""


async def open_forward_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.edit_message_text(
            PANEL, parse_mode=ParseMode.MARKDOWN, reply_markup=back_home()
        )
    else:
        await update.effective_message.reply_text(
            PANEL, parse_mode=ParseMode.MARKDOWN, reply_markup=back_home()
        )


@admin_only
async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "用法：`/fw_add 源 目标 [规则名]`", parse_mode=ParseMode.MARKDOWN
        )
        return
    source = context.args[0]
    target = context.args[1]
    name = " ".join(context.args[2:]) if len(context.args) > 2 else f"{source}→{target}"

    async with SessionLocal() as s:
        rule = ForwardRule(name=name, source_chat=source, target_chat=target)
        s.add(rule)
        await s.commit()
        await s.refresh(rule)
    await update.effective_message.reply_text(
        f"✅ 已添加搬运规则 #{rule.id}\n{name}\n（需重启或 /fw_reload 通知 user-bot）"
    )


@admin_only
async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as s:
        rules = (await s.execute(select(ForwardRule).order_by(ForwardRule.id))).scalars().all()
    if not rules:
        await update.effective_message.reply_text("📭 暂无规则")
        return
    lines = ["📡 *搬运规则*\n"]
    for r in rules:
        status = "✅" if r.enabled else "🚫"
        lines.append(
            f"{status} `#{r.id}` *{r.name}*\n"
            f"   {r.source_chat} → {r.target_chat}\n"
            f"   已转发 {r.forwarded_count} 条"
        )
        if r.keywords:
            lines.append(f"   关键词：{r.keywords}")
        if r.blacklist:
            lines.append(f"   黑名单：{r.blacklist}")
        if r.replace_from:
            lines.append(f"   替换：`{r.replace_from}` => `{r.replace_to or ''}`")
    await update.effective_message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.MARKDOWN
    )


@admin_only
async def del_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("用法：`/fw_del <id>`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        rid = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ id 必须是数字")
        return
    async with SessionLocal() as s:
        rule = await s.get(ForwardRule, rid)
        if not rule:
            await update.effective_message.reply_text("❌ 规则不存在")
            return
        await s.delete(rule)
        await s.commit()
    await update.effective_message.reply_text(f"🗑 已删除 #{rid}")


@admin_only
async def toggle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("用法：`/fw_toggle <id>`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        rid = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ id 必须是数字")
        return
    async with SessionLocal() as s:
        rule = await s.get(ForwardRule, rid)
        if not rule:
            await update.effective_message.reply_text("❌ 规则不存在")
            return
        rule.enabled = not rule.enabled
        await s.commit()
        state = "启用 ✅" if rule.enabled else "停用 🚫"
    await update.effective_message.reply_text(f"#{rid} 已 {state}")


@admin_only
async def filter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "用法：`/fw_filter <id> keywords=a,b | blacklist=c,d`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    try:
        rid = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ id 必须是数字")
        return
    body = " ".join(context.args[1:])
    parts = [p.strip() for p in body.split("|")]
    kw = None
    bl = None
    for p in parts:
        if p.startswith("keywords="):
            kw = p[len("keywords="):].strip() or None
        elif p.startswith("blacklist="):
            bl = p[len("blacklist="):].strip() or None
    async with SessionLocal() as s:
        rule = await s.get(ForwardRule, rid)
        if not rule:
            await update.effective_message.reply_text("❌ 规则不存在")
            return
        if kw is not None:
            rule.keywords = kw
        if bl is not None:
            rule.blacklist = bl
        await s.commit()
    await update.effective_message.reply_text(f"✅ 已更新 #{rid} 的过滤设置")


@admin_only
async def replace_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw = update.effective_message.text or ""
    after_cmd = raw.split(maxsplit=1)
    if len(after_cmd) < 2:
        await update.effective_message.reply_text(
            "用法：`/fw_replace <id> 原文 => 新文`", parse_mode=ParseMode.MARKDOWN
        )
        return
    body = after_cmd[1]
    parts = body.split(maxsplit=1)
    if len(parts) < 2 or "=>" not in parts[1]:
        await update.effective_message.reply_text(
            "用法：`/fw_replace <id> 原文 => 新文`", parse_mode=ParseMode.MARKDOWN
        )
        return
    try:
        rid = int(parts[0])
    except ValueError:
        await update.effective_message.reply_text("❌ id 必须是数字")
        return
    src, _, dst = parts[1].partition("=>")
    src = src.strip()
    dst = dst.strip()
    async with SessionLocal() as s:
        rule = await s.get(ForwardRule, rid)
        if not rule:
            await update.effective_message.reply_text("❌ 规则不存在")
            return
        rule.replace_from = src or None
        rule.replace_to = dst or None
        await s.commit()
    await update.effective_message.reply_text(f"✅ 已更新 #{rid} 文本替换")
