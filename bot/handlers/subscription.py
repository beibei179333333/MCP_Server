"""订阅 / 付费：套餐列表、订阅状态、管理员开通。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ..config import settings
from ..database import Payment, SessionLocal, Subscription, SubscriptionPlan, User
from ..keyboards import back_home
from ..utils import admin_only, is_admin, upsert_user

log = logging.getLogger(__name__)


async def plans_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await upsert_user(update)
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                select(SubscriptionPlan)
                .where(SubscriptionPlan.enabled.is_(True))
                .order_by(SubscriptionPlan.sort_order)
            )
        ).scalars().all()

    if not rows:
        await update.effective_message.reply_text("📭 当前没有可订阅的套餐")
        return

    lines = ["💎 *订阅套餐*\n"]
    btns = []
    for p in rows:
        price = "免费" if p.price == 0 else f"{p.price} {p.currency}"
        lines.append(
            f"*{p.name}* · `{p.code}` — {price} / {p.duration_days} 天\n"
            f"  {p.description or ''}\n"
            f"  特性：{p.features or '—'}"
        )
        btns.append([InlineKeyboardButton(f"订阅 {p.name}", callback_data=f"sub:buy:{p.code}")])

    btns.append([InlineKeyboardButton("🪪 我的订阅", callback_data="sub:my")])
    btns.append([InlineKeyboardButton("« 返回", callback_data="menu:home")])
    await update.effective_message.reply_text(
        "\n\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(btns),
    )


async def my_sub_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await upsert_user(update)
    uid = update.effective_user.id
    async with SessionLocal() as s:
        sub = (
            await s.execute(
                select(Subscription, SubscriptionPlan)
                .join(SubscriptionPlan, SubscriptionPlan.id == Subscription.plan_id)
                .where(Subscription.user_id == uid, Subscription.status == "active")
                .order_by(Subscription.expires_at.desc())
                .limit(1)
            )
        ).first()
    if not sub:
        await update.effective_message.reply_text(
            "📭 你还没有有效订阅。\n使用 /plans 查看套餐。",
            reply_markup=back_home(),
        )
        return
    s_obj, plan = sub
    days_left = (s_obj.expires_at - datetime.utcnow()).days
    await update.effective_message.reply_text(
        f"💎 当前订阅：*{plan.name}*\n"
        f"开始：{s_obj.started_at:%Y-%m-%d}\n"
        f"到期：{s_obj.expires_at:%Y-%m-%d}（剩 {days_left} 天）\n"
        f"特性：{plan.features or '—'}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_home(),
    )


async def subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    action = parts[1]
    if action == "my":
        await my_sub_cmd(update, context)
        return
    if action == "buy" and len(parts) > 2:
        code = parts[2]
        async with SessionLocal() as s:
            plan = (
                await s.execute(select(SubscriptionPlan).where(SubscriptionPlan.code == code))
            ).scalar_one_or_none()
        if not plan:
            await query.edit_message_text("❌ 套餐不存在", reply_markup=back_home())
            return

        if plan.price == 0:
            # 试用：直接发放
            await _grant(update.effective_user.id, plan)
            await query.edit_message_text(
                f"🎁 已激活 *{plan.name}*，有效 {plan.duration_days} 天",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=back_home(),
            )
            return

        # 付费：生成订单，提示用户付款
        async with SessionLocal() as s:
            pay = Payment(
                user_id=update.effective_user.id,
                plan_id=plan.id,
                amount=plan.price,
                currency=plan.currency,
                method="manual",
                status="pending",
            )
            s.add(pay)
            await s.commit()
            await s.refresh(pay)
        admins = ", ".join(f"`{a}`" for a in settings.admin_ids)
        await query.edit_message_text(
            f"💳 *订单已创建* #{pay.id}\n"
            f"套餐：*{plan.name}*\n"
            f"金额：*{plan.price} {plan.currency}*\n\n"
            f"请按以下任一方式支付，并把 *订单号 + 截图* 发给管理员开通：\n"
            f"• USDT (TRC20): `TYourWalletAddressHere`\n"
            f"• 支付宝 / 微信：联系管理员索取二维码\n"
            f"• Telegram Stars：管理员可代发 invoice\n\n"
            f"管理员：{admins}\n"
            f"开通后通过 /mysub 查询状态。",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_home(),
        )


async def _grant(user_id: int, plan: SubscriptionPlan) -> Subscription:
    async with SessionLocal() as s:
        sub = Subscription(
            user_id=user_id,
            plan_id=plan.id,
            status="active",
            started_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=plan.duration_days),
        )
        s.add(sub)
        await s.commit()
        await s.refresh(sub)
    # 触发返佣（仅付费套餐）
    if plan.price > 0:
        try:
            from .referral import credit_referral_commission
            await credit_referral_commission(user_id, plan.price)
        except Exception as e:  # noqa: BLE001
            log.warning("返佣失败: %s", e)
    return sub


@admin_only
async def grant_sub_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/grant_sub <user_id> <plan_code>"""
    if len(context.args) < 2:
        await update.effective_message.reply_text("用法：`/grant_sub <user_id> <plan_code>`")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("❌ user_id 必须为数字")
        return
    code = context.args[1]
    async with SessionLocal() as s:
        plan = (
            await s.execute(select(SubscriptionPlan).where(SubscriptionPlan.code == code))
        ).scalar_one_or_none()
    if not plan:
        await update.effective_message.reply_text(f"❌ 套餐 `{code}` 不存在")
        return
    sub = await _grant(uid, plan)
    await update.effective_message.reply_text(
        f"✅ 已为 `{uid}` 开通 *{plan.name}*，到期 {sub.expires_at:%Y-%m-%d}",
        parse_mode=ParseMode.MARKDOWN,
    )
    try:
        await context.bot.send_message(
            uid,
            f"🎉 你的订阅已开通：*{plan.name}*\n到期：{sub.expires_at:%Y-%m-%d}",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        pass


@admin_only
async def payments_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                select(Payment).order_by(Payment.id.desc()).limit(20)
            )
        ).scalars().all()
    if not rows:
        await update.effective_message.reply_text("📭 暂无支付记录")
        return
    lines = ["💳 *最近订单*\n"]
    for p in rows:
        lines.append(
            f"`#{p.id}` user `{p.user_id}` · {p.amount} {p.currency} · "
            f"{p.status} · {p.created_at:%m-%d %H:%M}"
        )
    await update.effective_message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.MARKDOWN
    )


async def user_has_active(user_id: int) -> bool:
    """供其他模块查询订阅状态。"""
    if user_id in settings.admin_ids:
        return True
    async with SessionLocal() as s:
        row = (
            await s.execute(
                select(Subscription).where(
                    Subscription.user_id == user_id,
                    Subscription.status == "active",
                    Subscription.expires_at > datetime.utcnow(),
                )
            )
        ).scalar_one_or_none()
    return row is not None
