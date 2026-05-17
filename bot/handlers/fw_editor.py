"""搬运规则可视化向导 + 编辑器：全程按钮，不用记命令。"""
from __future__ import annotations

import logging

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ..database import ForwardRule, SessionLocal
from ..utils import is_admin, short
from ..userbot import manager

log = logging.getLogger(__name__)


# =============================================================
# 可视化编辑器键盘
# =============================================================
def rule_editor_kb(rule: ForwardRule) -> InlineKeyboardMarkup:
    toggle_label = "⏸ 停用" if rule.enabled else "▶️ 启用"
    sender_label = "🤖 改用 Bot 发" if rule.sender == "user" else "👤 改用 User 发"
    rows = [
        [InlineKeyboardButton(toggle_label, callback_data=f"fwed:toggle:{rule.id}")],
        [InlineKeyboardButton("🔍 过滤词", callback_data=f"fwed:filter:{rule.id}"),
         InlineKeyboardButton("🔄 替换", callback_data=f"fwed:replace:{rule.id}")],
        [InlineKeyboardButton("📝 前后缀", callback_data=f"fwed:caption:{rule.id}"),
         InlineKeyboardButton("🔘 按钮", callback_data=f"fwed:buttons:{rule.id}")],
        [InlineKeyboardButton("📂 文件夹", callback_data=f"fwed:folder:{rule.id}"),
         InlineKeyboardButton(sender_label, callback_data=f"fwed:sender:{rule.id}")],
        [InlineKeyboardButton("⚡ 历史回填", callback_data=f"fwed:backfill:{rule.id}"),
         InlineKeyboardButton("🧪 测试", callback_data=f"fwed:test:{rule.id}")],
        [InlineKeyboardButton("🗑 删除", callback_data=f"fwed:del:{rule.id}")],
        [InlineKeyboardButton("« 返回列表", callback_data="fwlist:1"),
         InlineKeyboardButton("🏠 主菜单", callback_data="menu:home")],
    ]
    return InlineKeyboardMarkup(rows)


def _rule_summary(rule: ForwardRule) -> str:
    status = "✅ 启用" if rule.enabled else "🚫 停用"
    plugins = rule.plugins or {}
    fil = plugins.get("filter") or {}
    rep = plugins.get("replace") or {}
    cap = plugins.get("caption") or {}
    btn = plugins.get("buttons") or {}
    lines = [
        f"📡 *规则 #{rule.id}*  ({status})",
        f"📛 {rule.name}",
        f"📥 源：`{rule.source_chat}`",
        f"📤 目标：`{rule.targets}`",
        f"📂 文件夹：{rule.folder or '(无)'}",
        f"👤 发送身份：{rule.sender or 'user'}",
        f"📊 已转 {rule.forwarded_count} · 丢弃 {rule.dropped_count}",
        "",
        "*插件配置：*",
    ]
    if fil.get("keywords"):
        lines.append(f"  ✅ 关键词：{','.join(fil['keywords'])}")
    if fil.get("blacklist"):
        lines.append(f"  🚫 屏蔽词：{','.join(fil['blacklist'])}")
    if rep.get("rules"):
        for r in rep["rules"]:
            lines.append(f"  🔄 `{r.get('from','')}` → `{r.get('to','')}`")
    if cap.get("header"):
        lines.append(f"  📝 前缀：{short(cap['header'], 30)}")
    if cap.get("footer"):
        lines.append(f"  📝 后缀：{short(cap['footer'], 30)}")
    if btn.get("rows"):
        n = sum(len(r) for r in btn["rows"])
        lines.append(f"  🔘 按钮：{n} 个")
    if rule.sync_edits:
        lines.append("  ✏️ 编辑同步：开")
    if rule.sync_deletes:
        lines.append("  🗑 删除同步：开")
    if not any([fil, rep, cap, btn]):
        lines.append("  （暂无插件，全部原样转发）")
    return "\n".join(lines)


async def show_rule(update: Update, context: ContextTypes.DEFAULT_TYPE, rule_id: int) -> None:
    async with SessionLocal() as s:
        rule = await s.get(ForwardRule, rule_id)
    if not rule:
        await _reply_or_edit(update, "❌ 规则不存在", None)
        return
    await _reply_or_edit(update, _rule_summary(rule), rule_editor_kb(rule))


async def _reply_or_edit(update, text, kb):
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb
            )
            return
        except Exception:
            pass
    if update.effective_message:
        await update.effective_message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb
        )


# =============================================================
# 主回调路由
# =============================================================
async def editor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not is_admin(update.effective_user.id):
        return
    parts = q.data.split(":")
    if len(parts) < 2:
        return
    action = parts[1]

    # ---- 新建向导入口 ----
    if action == "new":
        context.user_data["flow"] = {"type": "fw_wizard", "step": "source", "data": {}}
        await q.edit_message_text(
            "📡 *新建搬运* — 第 1/3 步\n\n"
            "请告诉我*源*在哪：\n\n"
            "• 公开频道/群：发 `@channelname`\n"
            "• 私有频道：发 `-100xxxxxxxxxx` 数字 ID\n"
            "• 不知道 ID？把源里的任意一条消息**转发**给我\n\n"
            "回 /cancel 取消",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # 后续都需要 rule_id
    if len(parts) < 3:
        return
    try:
        rule_id = int(parts[2])
    except ValueError:
        return

    # ---- 打开编辑器 ----
    if action == "open":
        await show_rule(update, context, rule_id)
        return

    async with SessionLocal() as s:
        rule = await s.get(ForwardRule, rule_id)
    if not rule:
        await q.edit_message_text("❌ 规则不存在")
        return

    # ---- 一键开关 ----
    if action == "toggle":
        async with SessionLocal() as s:
            r = await s.get(ForwardRule, rule_id)
            r.enabled = not r.enabled
            await s.commit()
            await s.refresh(r)
        manager.request_reload()
        await show_rule(update, context, rule_id)
        return

    # ---- 一键切发送身份 ----
    if action == "sender":
        async with SessionLocal() as s:
            r = await s.get(ForwardRule, rule_id)
            r.sender = "bot" if (r.sender or "user") == "user" else "user"
            await s.commit()
        manager.request_reload()
        await show_rule(update, context, rule_id)
        return

    # ---- 删除（先确认）----
    if action == "del":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚠️ 确认删除", callback_data=f"fwed:delok:{rule_id}"),
             InlineKeyboardButton("« 取消", callback_data=f"fwed:open:{rule_id}")],
        ])
        await q.edit_message_text(
            f"🗑 确认删除规则 #{rule_id} *{rule.name}* ？\n此操作不可撤销。",
            parse_mode=ParseMode.MARKDOWN, reply_markup=kb,
        )
        return
    if action == "delok":
        async with SessionLocal() as s:
            r = await s.get(ForwardRule, rule_id)
            if r:
                await s.delete(r)
                await s.commit()
        manager.request_reload()
        await q.edit_message_text(f"✅ 规则 #{rule_id} 已删除")
        return

    # ---- 启动子向导（要用户输入文本） ----
    prompts = {
        "filter": (
            "🔍 *设置过滤词*\n\n"
            "发送格式：`关键词 :: 屏蔽词`\n（任一为空则用 - 占位）\n\n"
            "示例：\n"
            "  `优惠,折扣 :: 广告,赌博` — 必须含「优惠/折扣」且不含「广告/赌博」\n"
            "  `- :: 9G.com,52.com` — 只屏蔽，不限制关键词\n"
            "  `优惠 :: -` — 只要关键词，无屏蔽\n\n"
            "回 `clear` 清除过滤  ·  /cancel 取消"
        ),
        "replace": (
            "🔄 *添加文本替换*\n\n"
            "发送格式：`原文 => 新文`\n\n"
            "示例：\n"
            "  `@oldchannel => @mychannel`\n"
            "  `xxx.com => mysite.com`\n\n"
            "可多次添加。回 `clear` 清除全部  ·  /cancel 取消"
        ),
        "caption": (
            "📝 *设置前后缀*\n\n"
            "发送格式：`前缀 || 后缀`\n（任一为空则用 - 占位）\n\n"
            "示例：\n"
            "  `🔥 转载\\n || \\n—— @MyChannel`\n"
            "  `- || \\n关注我们`\n\n"
            "回 `clear` 清除  ·  /cancel 取消"
        ),
        "buttons": (
            "🔘 *设置按钮*\n\n"
            "发送格式：`标签1|URL1 ; 标签2|URL2`\n\n"
            "示例：\n"
            "  `关注频道|https://t.me/x ; 联系客服|https://t.me/cs`\n\n"
            "回 `clear` 清除  ·  /cancel 取消"
        ),
        "folder": (
            "📂 *设置文件夹*\n\n"
            "直接发送文件夹名（如 `新闻` `电商` `加密币`）\n\n"
            "回 `clear` 清除分组  ·  /cancel 取消"
        ),
        "backfill": (
            "⚡ *历史回填*\n\n"
            "发送要回填的条数（如 `200`）\n回 /cancel 取消"
        ),
        "test": (
            "🧪 *测试规则*\n\n"
            "发送一段样本文本，我会告诉你这条规则会**转发**还是**丢弃**\n回 /cancel 取消"
        ),
    }
    if action in prompts:
        context.user_data["flow"] = {
            "type": "fw_edit", "field": action, "rule_id": rule_id,
        }
        await q.edit_message_text(
            prompts[action], parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« 取消并返回", callback_data=f"fwed:open:{rule_id}")]
            ]),
        )
        return


# =============================================================
# 文字输入处理（向导 + 编辑器子步骤）
# =============================================================
async def handle_wizard_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """返回 True 表示已消化此条文本。"""
    flow = context.user_data.get("flow") or {}
    ftype = flow.get("type")
    if ftype == "fw_wizard":
        return await _handle_wizard(update, context, flow)
    if ftype == "fw_edit":
        return await _handle_edit(update, context, flow)
    return False


def _extract_chat_from_msg(msg) -> str | None:
    """从转发消息提取源 chat 标识。"""
    fo = getattr(msg, "forward_origin", None)
    if fo:
        c = getattr(fo, "chat", None) or getattr(fo, "sender_chat", None)
        if c:
            if getattr(c, "username", None):
                return "@" + c.username
            return str(c.id)
    return None


async def _handle_wizard(update, context, flow) -> bool:
    msg = update.effective_message
    text = (msg.text or "").strip()
    if text.lower() in ("/cancel", "cancel"):
        context.user_data.pop("flow", None)
        await msg.reply_text("✅ 已取消新建")
        return True

    step = flow["step"]
    data = flow["data"]

    if step == "source":
        src = _extract_chat_from_msg(msg) or text
        data["source"] = src
        flow["step"] = "target"
        await msg.reply_text(
            f"✅ 源：`{src}`\n\n📡 *新建搬运* — 第 2/3 步\n\n"
            "请告诉我*目标*在哪（同样格式，多目标用逗号分隔）：",
            parse_mode=ParseMode.MARKDOWN,
        )
        return True

    if step == "target":
        tgt = _extract_chat_from_msg(msg) or text
        data["target"] = tgt
        flow["step"] = "blacklist"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚫 不过滤，全部搬", callback_data="fwwz:skip_bl")]
        ])
        await msg.reply_text(
            f"✅ 目标：`{tgt}`\n\n📡 *新建搬运* — 第 3/3 步\n\n"
            "要屏蔽的*关键词*？（多个逗号分隔，如 `广告,9G.com,赌博`）\n"
            "不想过滤就按下面按钮：",
            parse_mode=ParseMode.MARKDOWN, reply_markup=kb,
        )
        return True

    if step == "blacklist":
        bl = [w.strip() for w in text.split(",") if w.strip()]
        await _finalize_wizard(update, context, data, bl)
        return True

    return False


async def _finalize_wizard(update, context, data, blacklist):
    plugins = {"filter": {"blacklist": blacklist}} if blacklist else {}
    async with SessionLocal() as s:
        rule = ForwardRule(
            name=f"{data['source']}→{data['target']}",
            source_chat=data["source"], targets=data["target"],
            plugins=plugins,
        )
        s.add(rule)
        await s.commit()
        await s.refresh(rule)
    context.user_data.pop("flow", None)
    manager.request_reload()
    summary = (
        f"✅ *规则 #{rule.id} 创建成功，已生效！*\n\n"
        f"📥 {data['source']}\n📤 {data['target']}\n"
    )
    if blacklist:
        summary += f"🚫 屏蔽：{','.join(blacklist)}\n"
    await update.effective_message.reply_text(
        summary, parse_mode=ParseMode.MARKDOWN, reply_markup=rule_editor_kb(rule),
    )


async def wizard_skip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 fwwz:* 向导按钮（如 跳过过滤）"""
    q = update.callback_query
    await q.answer()
    flow = context.user_data.get("flow") or {}
    if flow.get("type") != "fw_wizard":
        return
    if q.data == "fwwz:skip_bl":
        await _finalize_wizard(update, context, flow["data"], [])


async def _handle_edit(update, context, flow) -> bool:
    msg = update.effective_message
    text = (msg.text or "").strip()
    if text.lower() in ("/cancel", "cancel"):
        context.user_data.pop("flow", None)
        await msg.reply_text("✅ 已取消编辑")
        await show_rule(update, context, flow["rule_id"])
        return True

    field = flow["field"]
    rule_id = flow["rule_id"]
    async with SessionLocal() as s:
        rule = await s.get(ForwardRule, rule_id)
        if not rule:
            await msg.reply_text("❌ 规则不存在")
            context.user_data.pop("flow", None)
            return True
        cfg = dict(rule.plugins or {})

        if text.lower() == "clear":
            if field == "filter":
                cfg.pop("filter", None)
            elif field == "replace":
                cfg.pop("replace", None)
            elif field == "caption":
                cfg.pop("caption", None)
            elif field == "buttons":
                cfg.pop("buttons", None)
            elif field == "folder":
                rule.folder = None
            rule.plugins = cfg
            await s.commit()
            context.user_data.pop("flow", None)
            await msg.reply_text(f"✅ 已清除 #{rule_id} 的 {field}")
            await show_rule(update, context, rule_id)
            return True

        if field == "filter":
            if "::" not in text:
                await msg.reply_text("⚠️ 格式：`关键词 :: 屏蔽词`，空用 - 占位")
                return True
            kw_part, bl_part = [x.strip() for x in text.split("::", 1)]
            f = {}
            if kw_part and kw_part != "-":
                f["keywords"] = [w.strip() for w in kw_part.split(",") if w.strip()]
            if bl_part and bl_part != "-":
                f["blacklist"] = [w.strip() for w in bl_part.split(",") if w.strip()]
            cfg["filter"] = f or {}

        elif field == "replace":
            if "=>" not in text:
                await msg.reply_text("⚠️ 格式：`原文 => 新文`")
                return True
            src, _, dst = text.partition("=>")
            rules = list((cfg.get("replace") or {}).get("rules", []))
            rules.append({"from": src.strip(), "to": dst.strip(), "regex": False})
            cfg["replace"] = {"rules": rules}

        elif field == "caption":
            if "||" not in text:
                await msg.reply_text("⚠️ 格式：`前缀 || 后缀`")
                return True
            header, _, footer = text.partition("||")
            c = {}
            if header.strip() and header.strip() != "-":
                c["header"] = header.strip().replace("\\n", "\n")
            if footer.strip() and footer.strip() != "-":
                c["footer"] = footer.strip().replace("\\n", "\n")
            cfg["caption"] = c

        elif field == "buttons":
            rows = []
            for seg in text.split(";"):
                seg = seg.strip()
                if "|" not in seg:
                    continue
                lab, url = seg.split("|", 1)
                rows.append([{"label": lab.strip(), "url": url.strip()}])
            cfg["buttons"] = {"rows": rows} if rows else {}

        elif field == "folder":
            rule.folder = text

        elif field == "backfill":
            try:
                limit = int(text)
            except ValueError:
                await msg.reply_text("⚠️ 请发数字")
                return True
            context.user_data.pop("flow", None)
            await msg.reply_text(f"⏳ 开始回填 {limit} 条…")
            result = await manager.backfill(rule_id, limit=limit)
            if not result.get("ok"):
                await msg.reply_text(f"❌ {result.get('err')}")
            else:
                await msg.reply_text(
                    f"✅ 回填完成：成功 {result['sent']} · 丢弃 {result['dropped']}"
                )
            await show_rule(update, context, rule_id)
            return True

        elif field == "test":
            from ..plugins import MessageContext, build_chain
            ctx = MessageContext(text=text, caption=text, media_type="text")
            ctx.extra["rule_id"] = rule_id
            chain = build_chain(rule.plugins or {})
            ok = await chain.run(ctx)
            verdict = "✅ 会*转发*" if ok else "❌ 会*丢弃*"
            await msg.reply_text(
                f"{verdict}\n\n原文：{text}\n处理后：{ctx.text}",
                parse_mode=ParseMode.MARKDOWN,
            )
            # 不退出编辑模式，继续测试
            return True

        rule.plugins = cfg
        await s.commit()
        await s.refresh(rule)

    context.user_data.pop("flow", None)
    manager.request_reload()
    await msg.reply_text(f"✅ 已更新 #{rule_id} 的 {field}")
    await show_rule(update, context, rule_id)
    return True
