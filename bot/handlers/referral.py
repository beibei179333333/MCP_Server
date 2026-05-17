"""推广返佣 / MMO：邀请人记录、积分累计、提现申请。"""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ..config import settings
from ..database import SessionLocal, User, Withdrawal
from ..keyboards import back_home
from ..utils import admin_only, upsert_user

log = logging.getLogger(__name__)


async def _bind_referrer(user_id: int, referrer_id: int) -> bool:
    """绑定推荐人；已有推荐人则跳过。"""
    if user_id == referrer_id:
        return False
    async with SessionLocal() as s:
        u = await s.get(User, user_id)
        if not u or u.referrer_id:
            return False
        ref = await s.get(User, referrer_id)
        if not ref:
            return False
        u.referrer_id = referrer_id
        ref.referrals = (ref.referrals or 0) + 1
        await s.commit()
    return True


async def handle_start_payload(update: Update, payload: str) -> None:
    """/start ref_xxx 形式：xxx 是推荐人的 user_id"""
    if not payload.startswith("ref_"):
        return
    try:
        rid = int(payload[4:])
    except ValueError:
        return
    if await _bind_referrer(update.effective_user.id, rid):
        log.info("用户 %s 被推荐人 %s 邀请", update.effective_user.id, rid)


async def myref_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await upsert_user(update)
    me = await context.bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{update.effective_user.id}"
    uid = update.effective_user.id
    async with SessionLocal() as s:
        u = await s.get(User, uid)
        invited = u.referrals if u else 0
        points = u.points if u else 0
    pct = int(settings.referral_commission * 100)
    text = (
        "🎁 *推广返佣*\n\n"
        f"你的专属邀请链接：\n`{link}`\n\n"
        f"每位被邀请用户购买订阅时，你获得其订阅金额的 *{pct}%* 作为积分（1 积分 = 1 元）。\n\n"
        f"📊 *我的数据*\n"
        f"• 已邀请：*{invited}* 人\n"
        f"• 累计积分：*{points}* 分\n"
        f"• 满 {int(settings.referral_min_withdraw)} 分可申请提现\n\n"
        f"使用 /withdraw 申请提现 · /toplist 看排行榜"
    )
    await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=back_home())


async def withdraw_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/withdraw <方式> <账号>"""
    await upsert_user(update)
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "用法：`/withdraw <方式> <账号>`\n"
            "示例：`/withdraw usdt TQRy123...`、`/withdraw alipay 13800138000`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    method = context.args[0].lower()
    account = " ".join(context.args[1:])
    uid = update.effective_user.id
    async with SessionLocal() as s:
        u = await s.get(User, uid)
        if not u or (u.points or 0) < settings.referral_min_withdraw:
            await update.effective_message.reply_text(
                f"❌ 积分不足 {int(settings.referral_min_withdraw)}，无法提现"
            )
            return
        amount = float(u.points)
        w = Withdrawal(
            user_id=uid, points=u.points, amount=amount, method=method, account=account,
        )
        s.add(w)
        u.points = 0
        await s.commit()
        await s.refresh(w)
    await update.effective_message.reply_text(
        f"✅ 提现申请 #{w.id} 已提交\n"
        f"金额：{amount:.2f}\n方式：{method}\n账号：{account}\n\n"
        f"管理员审核后会打款。请耐心等待。"
    )
    # 通知所有管理员
    for admin_id in settings.admin_ids:
        try:
            await context.bot.send_message(
                admin_id,
                f"💸 *提现申请* #{w.id}\n"
                f"用户：`{uid}` ({u.username or '—'})\n"
                f"金额：{amount:.2f}  方式：{method}\n"
                f"账号：`{account}`\n\n"
                f"通过：`/wd_approve {w.id}`\n"
                f"驳回：`/wd_reject {w.id} 原因`",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            pass


async def toplist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                select(User).where(User.referrals > 0)
                .order_by(User.referrals.desc()).limit(10)
            )
        ).scalars().all()
    if not rows:
        await update.effective_message.reply_text("📭 还没有人邀请用户")
        return
    lines = ["🏆 *邀请榜 Top 10*\n"]
    for i, u in enumerate(rows, 1):
        medal = "🥇🥈🥉"[i - 1] if i <= 3 else f"{i}."
        name = u.username or u.first_name or f"id:{u.id}"
        lines.append(f"{medal} {name} — *{u.referrals}* 人邀 · {u.points} 积分")
    await update.effective_message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.MARKDOWN
    )


@admin_only
async def wd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("用法：`/wd_approve <id>`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        wid = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ id 必须是数字")
        return
    from datetime import datetime
    async with SessionLocal() as s:
        w = await s.get(Withdrawal, wid)
        if not w:
            await update.effective_message.reply_text("❌ 申请不存在")
            return
        w.status = "settled"
        w.settled_at = datetime.utcnow()
        await s.commit()
    await update.effective_message.reply_text(f"✅ 提现 #{wid} 标记为已结算")
    try:
        await context.bot.send_message(
            w.user_id, f"💸 你的提现 #{wid}（{w.amount:.2f}）已打款，请查收。"
        )
    except Exception:
        pass


@admin_only
async def wd_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 1:
        await update.effective_message.reply_text("用法：`/wd_reject <id> [原因]`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        wid = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ id 必须是数字")
        return
    reason = " ".join(context.args[1:]) or "不符合规则"
    async with SessionLocal() as s:
        w = await s.get(Withdrawal, wid)
        if not w:
            await update.effective_message.reply_text("❌ 申请不存在")
            return
        # 退回积分
        u = await s.get(User, w.user_id)
        if u:
            u.points = (u.points or 0) + w.points
        w.status = "rejected"
        w.note = reason
        await s.commit()
    await update.effective_message.reply_text(f"❌ 提现 #{wid} 已驳回（已退回积分）")
    try:
        await context.bot.send_message(
            w.user_id,
            f"❌ 你的提现 #{wid} 被驳回\n原因：{reason}\n（积分已退回）",
        )
    except Exception:
        pass


async def credit_referral_commission(user_id: int, amount: float) -> None:
    """订阅付款成功后调用：给推荐人加积分。"""
    if amount <= 0:
        return
    async with SessionLocal() as s:
        u = await s.get(User, user_id)
        if not u or not u.referrer_id:
            return
        ref = await s.get(User, u.referrer_id)
        if not ref:
            return
        bonus = int(amount * settings.referral_commission)
        if bonus <= 0:
            return
        ref.points = (ref.points or 0) + bonus
        await s.commit()
    log.info("返佣：用户 %s 付款 %s，推荐人 %s +%s 积分", user_id, amount, u.referrer_id, bonus)
