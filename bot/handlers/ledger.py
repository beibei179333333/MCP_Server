"""记账：自然语言录入、报表、走势图、CSV 导出。"""
from __future__ import annotations

import csv
import io
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from telegram import InputFile, Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

from ..database import Budget, LedgerAccount, LedgerEntry, SessionLocal
from ..keyboards import back_home, ledger_menu
from ..utils import is_admin, month_range, parse_amount_note, today_range

log = logging.getLogger(__name__)
DEFAULT_ACCOUNT = "默认"


async def _get_or_create_default(owner_id: int) -> LedgerAccount:
    async with SessionLocal() as s:
        stmt = select(LedgerAccount).where(
            LedgerAccount.owner_id == owner_id, LedgerAccount.name == DEFAULT_ACCOUNT
        )
        acc = (await s.execute(stmt)).scalar_one_or_none()
        if not acc:
            acc = LedgerAccount(owner_id=owner_id, name=DEFAULT_ACCOUNT)
            s.add(acc)
            await s.commit()
            await s.refresh(acc)
        return acc


async def open_ledger_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📒 *记账面板*\n\n"
        "直接发送：`金额 类别 备注`\n"
        "示例：\n"
        "  `120 餐饮 午餐`  → 支出 120\n"
        "  `+5000 工资`     → 收入 5000\n"
        "  `-50 打车`       → 支出 50\n"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=ledger_menu()
        )
    else:
        await update.effective_message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=ledger_menu()
        )


async def ledger_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await open_ledger_panel(update, context)


async def quick_record(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    私聊文本：尝试解析为记账。返回 True 表示已处理。
    """
    msg = update.effective_message
    if not msg or not msg.text:
        return False
    if update.effective_chat.type != ChatType.PRIVATE:
        return False
    if msg.text.startswith("/"):
        return False

    amount, category, note = parse_amount_note(msg.text)
    if amount is None:
        return False

    owner_id = update.effective_user.id
    acc = await _get_or_create_default(owner_id)
    kind = "income" if amount > 0 else "expense"
    abs_amount = abs(amount)

    async with SessionLocal() as s:
        entry = LedgerEntry(
            account_id=acc.id,
            kind=kind,
            amount=abs_amount,
            category=category,
            note=note,
            occurred_at=datetime.utcnow(),
        )
        s.add(entry)
        await s.commit()
        await s.refresh(entry)

    sign = "📈 收入" if kind == "income" else "📉 支出"
    text = (
        f"{sign} *{abs_amount:.2f}* {acc.currency}\n"
        f"分类：{category}\n"
        + (f"备注：{note}\n" if note else "")
        + f"流水号 #{entry.id}"
    )
    await msg.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    if kind == "expense":
        try:
            await maybe_alert_budget(context.bot, owner_id, category)
        except Exception:
            pass
    return True


async def _summary(owner_id: int, start: datetime, end: datetime):
    async with SessionLocal() as s:
        stmt = (
            select(
                LedgerEntry.kind,
                LedgerEntry.category,
                func.sum(LedgerEntry.amount),
                func.count(LedgerEntry.id),
            )
            .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
            .where(
                LedgerAccount.owner_id == owner_id,
                LedgerEntry.occurred_at >= start,
                LedgerEntry.occurred_at < end,
            )
            .group_by(LedgerEntry.kind, LedgerEntry.category)
        )
        rows = (await s.execute(stmt)).all()

    income_total = 0.0
    expense_total = 0.0
    income_by_cat: dict[str, float] = defaultdict(float)
    expense_by_cat: dict[str, float] = defaultdict(float)
    count = 0
    for kind, category, total, cnt in rows:
        count += cnt
        if kind == "income":
            income_total += float(total)
            income_by_cat[category or "其他"] += float(total)
        else:
            expense_total += float(total)
            expense_by_cat[category or "其他"] += float(total)
    return income_total, expense_total, income_by_cat, expense_by_cat, count


def _format_summary(title: str, inc, exp, inc_cat, exp_cat, count) -> str:
    lines = [f"📊 *{title}*", ""]
    lines.append(f"📈 收入：*{inc:.2f}*")
    lines.append(f"📉 支出：*{exp:.2f}*")
    lines.append(f"💰 结余：*{inc - exp:.2f}*")
    lines.append(f"🧾 共 {count} 条")
    if exp_cat:
        lines.append("\n*支出分布：*")
        for cat, val in sorted(exp_cat.items(), key=lambda x: -x[1]):
            ratio = val / exp * 100 if exp > 0 else 0
            lines.append(f"  • {cat}: {val:.2f}  ({ratio:.1f}%)")
    if inc_cat:
        lines.append("\n*收入分布：*")
        for cat, val in sorted(inc_cat.items(), key=lambda x: -x[1]):
            lines.append(f"  • {cat}: {val:.2f}")
    return "\n".join(lines)


async def today_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    start, end = today_range()
    data = await _summary(update.effective_user.id, start, end)
    await update.effective_message.reply_text(
        _format_summary("今日汇总", *data),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ledger_menu(),
    )


async def month_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    start, end = month_range()
    data = await _summary(update.effective_user.id, start, end)
    await update.effective_message.reply_text(
        _format_summary(f"{start.strftime('%Y-%m')} 月度汇总", *data),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ledger_menu(),
    )


async def chart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """生成最近 30 天收支走势图。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        await update.effective_message.reply_text("⚠️ 未安装 matplotlib，无法生成图表")
        return

    end = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    start = end - timedelta(days=30)

    async with SessionLocal() as s:
        stmt = (
            select(LedgerEntry.occurred_at, LedgerEntry.kind, LedgerEntry.amount)
            .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
            .where(
                LedgerAccount.owner_id == update.effective_user.id,
                LedgerEntry.occurred_at >= start,
                LedgerEntry.occurred_at < end,
            )
        )
        rows = (await s.execute(stmt)).all()

    if not rows:
        await update.effective_message.reply_text("📭 近 30 天没有记账数据")
        return

    days = [(start + timedelta(days=i)).date() for i in range(30)]
    inc_map = {d: 0.0 for d in days}
    exp_map = {d: 0.0 for d in days}
    for occurred, kind, amount in rows:
        d = occurred.date()
        if d in inc_map:
            if kind == "income":
                inc_map[d] += float(amount)
            else:
                exp_map[d] += float(amount)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(days, [inc_map[d] for d in days], label="收入 Income", color="#2ecc71", marker="o", linewidth=2)
    ax.plot(days, [exp_map[d] for d in days], label="支出 Expense", color="#e74c3c", marker="o", linewidth=2)
    ax.set_title("Last 30 Days")
    ax.set_ylabel("Amount")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110)
    plt.close(fig)
    buf.seek(0)

    await update.effective_message.reply_photo(
        photo=InputFile(buf, filename="ledger.png"),
        caption="📈 最近 30 天收支走势",
    )


async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner_id = update.effective_user.id
    async with SessionLocal() as s:
        stmt = (
            select(
                LedgerEntry.occurred_at,
                LedgerEntry.kind,
                LedgerEntry.amount,
                LedgerEntry.category,
                LedgerEntry.note,
                LedgerAccount.name,
                LedgerAccount.currency,
            )
            .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
            .where(LedgerAccount.owner_id == owner_id)
            .order_by(LedgerEntry.occurred_at.desc())
        )
        rows = (await s.execute(stmt)).all()

    if not rows:
        await update.effective_message.reply_text("📭 暂无数据可导出")
        return

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["时间", "类型", "金额", "币种", "分类", "备注", "账户"])
    for occ, kind, amt, cat, note, acc_name, cur in rows:
        writer.writerow(
            [
                occ.strftime("%Y-%m-%d %H:%M:%S"),
                "收入" if kind == "income" else "支出",
                f"{amt:.2f}",
                cur,
                cat or "",
                note or "",
                acc_name,
            ]
        )
    data = out.getvalue().encode("utf-8-sig")  # BOM for Excel
    await update.effective_message.reply_document(
        document=InputFile(io.BytesIO(data), filename=f"ledger_{owner_id}.csv"),
        caption=f"📦 共导出 {len(rows)} 条流水",
    )


async def ledger_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理记账面板按钮。"""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "list" and len(parts) > 2 and parts[2] == "today":
        start, end = today_range()
        data = await _summary(update.effective_user.id, start, end)
        await query.edit_message_text(
            _format_summary("今日汇总", *data),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=ledger_menu(),
        )
    elif action == "report" and len(parts) > 2 and parts[2] == "month":
        start, end = month_range()
        data = await _summary(update.effective_user.id, start, end)
        await query.edit_message_text(
            _format_summary(f"{start.strftime('%Y-%m')} 月度汇总", *data),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=ledger_menu(),
        )
    elif action == "add" and len(parts) > 2:
        kind = parts[2]
        context.user_data["flow"] = {"type": "ledger_add", "kind": kind}
        sign = "收入" if kind == "income" else "支出"
        await query.edit_message_text(
            f"请发送 *{sign}* 内容，格式：`金额 类别 备注`\n例如：`120 餐饮 午餐`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_home(),
        )
    elif action == "accounts":
        await _show_accounts(update, context)
    elif action == "chart":
        await chart_cmd(update, context)
    else:
        await open_ledger_panel(update, context)


async def _show_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner_id = update.effective_user.id
    async with SessionLocal() as s:
        stmt = select(LedgerAccount).where(LedgerAccount.owner_id == owner_id)
        accounts = (await s.execute(stmt)).scalars().all()
    if not accounts:
        await _get_or_create_default(owner_id)
        accounts = [await _get_or_create_default(owner_id)]
    lines = ["🗂 *我的账户*\n"]
    for a in accounts:
        lines.append(f"• {a.name} ({a.currency})")
    lines.append("\n（多账户编辑功能开发中，默认账户已可用）")
    await update.callback_query.edit_message_text(
        "\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=ledger_menu()
    )


# =============================================================
# 预算 / 告警
# =============================================================
async def budget_set_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/budget <类别> <月限额>"""
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "用法：`/budget 餐饮 1500`", parse_mode=ParseMode.MARKDOWN
        )
        return
    category = context.args[0]
    try:
        limit = float(context.args[1])
    except ValueError:
        await update.effective_message.reply_text("❌ 金额必须为数字")
        return
    owner_id = update.effective_user.id
    async with SessionLocal() as s:
        stmt = select(Budget).where(
            Budget.owner_id == owner_id, Budget.category == category
        )
        b = (await s.execute(stmt)).scalar_one_or_none()
        if b:
            b.monthly_limit = limit
        else:
            s.add(Budget(owner_id=owner_id, category=category, monthly_limit=limit))
        await s.commit()
    await update.effective_message.reply_text(
        f"💰 已设置预算 *{category}* ＝ {limit:.2f} / 月", parse_mode=ParseMode.MARKDOWN
    )


async def budget_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner_id = update.effective_user.id
    start, end = month_range()
    async with SessionLocal() as s:
        budgets = (
            await s.execute(select(Budget).where(Budget.owner_id == owner_id))
        ).scalars().all()
        if not budgets:
            await update.effective_message.reply_text(
                "📭 还没有预算。用 `/budget 类别 金额` 设置。",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        # 当月已用
        used_stmt = (
            select(LedgerEntry.category, func.sum(LedgerEntry.amount))
            .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
            .where(
                LedgerAccount.owner_id == owner_id,
                LedgerEntry.kind == "expense",
                LedgerEntry.occurred_at >= start,
                LedgerEntry.occurred_at < end,
            )
            .group_by(LedgerEntry.category)
        )
        used = {cat or "其他": float(v) for cat, v in (await s.execute(used_stmt)).all()}

    lines = [f"💰 *本月预算*（{start:%Y-%m}）\n"]
    for b in budgets:
        u = used.get(b.category, 0.0)
        pct = u / b.monthly_limit * 100 if b.monthly_limit > 0 else 0
        bar = _bar(pct)
        flag = "🚨" if pct >= 100 else ("⚠️" if pct >= b.alert_threshold * 100 else "✅")
        lines.append(
            f"{flag} *{b.category}*  {u:.0f}/{b.monthly_limit:.0f}  ({pct:.0f}%)\n{bar}"
        )
    await update.effective_message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.MARKDOWN
    )


def _bar(pct: float, width: int = 20) -> str:
    pct = max(0, min(100, pct))
    fill = int(width * pct / 100)
    return "`" + "█" * fill + "░" * (width - fill) + "`"


async def maybe_alert_budget(bot, user_id: int, category: str) -> None:
    """每次记账后检查是否触发预算告警。"""
    if not category:
        return
    start, end = month_range()
    async with SessionLocal() as s:
        b = (
            await s.execute(
                select(Budget).where(
                    Budget.owner_id == user_id, Budget.category == category
                )
            )
        ).scalar_one_or_none()
        if not b:
            return
        used_stmt = (
            select(func.coalesce(func.sum(LedgerEntry.amount), 0))
            .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
            .where(
                LedgerAccount.owner_id == user_id,
                LedgerEntry.kind == "expense",
                LedgerEntry.category == category,
                LedgerEntry.occurred_at >= start,
                LedgerEntry.occurred_at < end,
            )
        )
        used = float((await s.execute(used_stmt)).scalar() or 0)
        pct = used / b.monthly_limit * 100 if b.monthly_limit > 0 else 0
        if pct < b.alert_threshold * 100:
            return
        # 同一阈值不重复提醒（每月每类别仅 1 次）
        if b.last_alert_at and b.last_alert_at >= start:
            return
        b.last_alert_at = datetime.utcnow()
        await s.commit()
    try:
        await bot.send_message(
            user_id,
            f"⚠️ *预算提醒*：*{category}* 本月已用 *{pct:.0f}%* "
            f"({used:.0f} / {b.monthly_limit:.0f})",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        pass
