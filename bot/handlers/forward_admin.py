"""搬运规则 CRUD（适配新插件 JSON 模型）。"""
from __future__ import annotations

import json
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
📡 *搬运规则管理（tgcf 风格插件链）*

命令：
• `/fw_add 源 目标 [规则名]` — 添加（目标用逗号分隔多目标）
• `/fw_list` — 列出
• `/fw_del <id>` — 删除
• `/fw_toggle <id>` — 启 / 停
• `/fw_filter <id> kw=A,B bl=C,D` — 关键词/黑名单
• `/fw_replace <id> 原文 => 新文` — 文本替换
• `/fw_caption <id> header=... | footer=...`
• `/fw_format <id> links=1 mentions=1 emoji=0`
• `/fw_media <id> allow=photo,video,text`
• `/fw_watermark <id> @MyChannel`
• `/fw_plugins <id>` — 查看完整 JSON
• `/fw_backfill <id> [limit=200]` — 历史回填
• `/fw_reload` — 通知 user-bot 重新加载

源 / 目标支持：`@username` 或数字 `-100xxx`
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
            "用法：`/fw_add 源 目标[,目标2] [规则名]`", parse_mode=ParseMode.MARKDOWN
        )
        return
    source = context.args[0]
    targets = context.args[1]
    name = " ".join(context.args[2:]) if len(context.args) > 2 else f"{source}→{targets}"
    async with SessionLocal() as s:
        rule = ForwardRule(name=name, source_chat=source, targets=targets, plugins={})
        s.add(rule)
        await s.commit()
        await s.refresh(rule)
    await update.effective_message.reply_text(
        f"✅ 添加规则 #{rule.id}\n{name}\n（运行 /fw_reload 让 user-bot 立即生效）"
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
        plugin_keys = ",".join((r.plugins or {}).keys()) or "—"
        lines.append(
            f"{status} `#{r.id}` *{r.name}*  ({r.mode})\n"
            f"   {r.source_chat} → {r.targets}\n"
            f"   插件: `{plugin_keys}` · 已转 {r.forwarded_count} · 丢弃 {r.dropped_count}"
        )
    await update.effective_message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.MARKDOWN
    )


@admin_only
async def del_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rid = await _arg_int(update, context)
    if rid is None:
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
    rid = await _arg_int(update, context)
    if rid is None:
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


async def _arg_int(update, context) -> int | None:
    if not context.args:
        await update.effective_message.reply_text("⚠️ 缺少 id 参数")
        return None
    try:
        return int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ id 必须是数字")
        return None


async def _update_plugin(update, context, key: str, build_cfg) -> None:
    rid = await _arg_int(update, context)
    if rid is None:
        return
    async with SessionLocal() as s:
        rule = await s.get(ForwardRule, rid)
        if not rule:
            await update.effective_message.reply_text("❌ 规则不存在")
            return
        cfg = dict(rule.plugins or {})
        new_cfg = build_cfg(rule, cfg.get(key, {}))
        if new_cfg is None:
            cfg.pop(key, None)
        else:
            cfg[key] = new_cfg
        rule.plugins = cfg
        await s.commit()
    await update.effective_message.reply_text(f"✅ 已更新 #{rid} 插件 `{key}`")


def _kv_parse(args: list[str]) -> dict:
    d: dict = {}
    for a in args:
        if "=" not in a:
            continue
        k, v = a.split("=", 1)
        d[k.strip()] = v.strip()
    return d


@admin_only
async def filter_cmd(update, context):
    """/fw_filter <id> kw=优惠,打折 bl=广告,垃圾"""
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "用法：`/fw_filter <id> kw=A,B bl=C,D`", parse_mode=ParseMode.MARKDOWN
        )
        return
    pairs = _kv_parse(context.args[1:])
    def build(_rule, _old):
        out = dict(_old)
        if "kw" in pairs:
            out["keywords"] = [x for x in pairs["kw"].split(",") if x]
        if "bl" in pairs:
            out["blacklist"] = [x for x in pairs["bl"].split(",") if x]
        return out or None
    await _update_plugin(update, context, "filter", build)


@admin_only
async def replace_cmd(update, context):
    """/fw_replace <id> 原文 => 新文"""
    raw = update.effective_message.text or ""
    parts = raw.split(maxsplit=2)  # /fw_replace id body
    if len(parts) < 3 or "=>" not in parts[2]:
        await update.effective_message.reply_text(
            "用法：`/fw_replace <id> 原文 => 新文`", parse_mode=ParseMode.MARKDOWN
        )
        return
    try:
        rid = int(parts[1])
    except ValueError:
        await update.effective_message.reply_text("❌ id 必须是数字")
        return
    src, _, dst = parts[2].partition("=>")
    context.args = [str(rid)]
    def build(_rule, _old):
        out = dict(_old)
        rules = list(out.get("rules", []))
        rules.append({"from": src.strip(), "to": dst.strip(), "regex": False})
        out["rules"] = rules
        return out
    await _update_plugin(update, context, "replace", build)


@admin_only
async def caption_cmd(update, context):
    """/fw_caption <id> header=🔥前缀 | footer=—@CH"""
    raw = update.effective_message.text or ""
    parts = raw.split(maxsplit=2)
    if len(parts) < 3:
        await update.effective_message.reply_text(
            "用法：`/fw_caption <id> header=... | footer=...`", parse_mode=ParseMode.MARKDOWN
        )
        return
    try:
        rid = int(parts[1])
    except ValueError:
        await update.effective_message.reply_text("❌ id 必须是数字")
        return
    body = parts[2]
    segs = [seg.strip() for seg in body.split("|")]
    header = footer = None
    for s in segs:
        if s.startswith("header="):
            header = s[len("header="):]
        elif s.startswith("footer="):
            footer = s[len("footer="):]
    context.args = [str(rid)]
    def build(_rule, _old):
        out = dict(_old)
        if header is not None:
            out["header"] = header
        if footer is not None:
            out["footer"] = footer
        return out or None
    await _update_plugin(update, context, "caption", build)


@admin_only
async def format_cmd(update, context):
    """/fw_format <id> links=1 mentions=1 emoji=0 collapse=1"""
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "用法：`/fw_format <id> links=1 mentions=1 emoji=0 collapse=1`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    pairs = _kv_parse(context.args[1:])
    def build(_rule, _old):
        out = dict(_old)
        out["strip_links"] = pairs.get("links", "0") in ("1", "true", "yes")
        out["strip_mentions"] = pairs.get("mentions", "0") in ("1", "true", "yes")
        out["strip_emoji"] = pairs.get("emoji", "0") in ("1", "true", "yes")
        out["collapse_newlines"] = pairs.get("collapse", "0") in ("1", "true", "yes")
        return out
    await _update_plugin(update, context, "format", build)


@admin_only
async def media_cmd(update, context):
    """/fw_media <id> allow=photo,video,text"""
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "用法：`/fw_media <id> allow=photo,video,text deny=document`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    pairs = _kv_parse(context.args[1:])
    def build(_rule, _old):
        out = dict(_old)
        if "allow" in pairs:
            out["allow"] = [x for x in pairs["allow"].split(",") if x]
        if "deny" in pairs:
            out["deny"] = [x for x in pairs["deny"].split(",") if x]
        return out or None
    await _update_plugin(update, context, "media", build)


@admin_only
async def watermark_cmd(update, context):
    """/fw_watermark <id> 水印文本"""
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "用法：`/fw_watermark <id> @MyChannel`", parse_mode=ParseMode.MARKDOWN
        )
        return
    text = " ".join(context.args[1:])
    def build(_rule, _old):
        out = dict(_old)
        out["text"] = text
        out.setdefault("position", "br")
        out.setdefault("opacity", 160)
        return out
    await _update_plugin(update, context, "watermark", build)


@admin_only
async def plugins_show(update, context):
    rid = await _arg_int(update, context)
    if rid is None:
        return
    async with SessionLocal() as s:
        rule = await s.get(ForwardRule, rid)
        if not rule:
            await update.effective_message.reply_text("❌ 规则不存在")
            return
        body = json.dumps(rule.plugins or {}, ensure_ascii=False, indent=2)
    await update.effective_message.reply_text(
        f"```json\n{body}\n```", parse_mode=ParseMode.MARKDOWN
    )


@admin_only
async def backfill_cmd(update, context):
    """/fw_backfill <id> [limit]"""
    if not context.args:
        await update.effective_message.reply_text(
            "用法：`/fw_backfill <id> [limit=200]`", parse_mode=ParseMode.MARKDOWN
        )
        return
    try:
        rid = int(context.args[0])
        limit = int(context.args[1]) if len(context.args) > 1 else 200
    except ValueError:
        await update.effective_message.reply_text("❌ 参数必须是数字")
        return
    await update.effective_message.reply_text(
        f"⏳ 开始回填规则 #{rid} 的最近 {limit} 条历史…"
    )
    from ..userbot import manager
    result = await manager.backfill(rid, limit=limit)
    if not result.get("ok"):
        await update.effective_message.reply_text(f"❌ {result.get('err')}")
        return
    await update.effective_message.reply_text(
        f"✅ 回填完成：成功 {result['sent']} 条，丢弃/跳过 {result['dropped']} 条"
    )
