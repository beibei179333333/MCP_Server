"""APScheduler 全局实例 + 定时任务注册。"""
from __future__ import annotations

import logging
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from .config import settings
from .database import (
    BroadcastJob,
    CaptchaSession,
    LedgerAccount,
    LedgerEntry,
    RecurringEntry,
    SessionLocal,
    Subscription,
)

log = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=pytz.timezone(settings.timezone))
_bot_app = None  # 在 main 启动后注入


def set_bot_app(app) -> None:
    global _bot_app
    _bot_app = app


# =============================================================
# 任务实现
# =============================================================
async def run_due_broadcasts() -> None:
    """触发到点的定时群发。"""
    from .handlers.broadcast import execute_job_id  # 延迟导入避免循环

    now = datetime.utcnow()
    async with SessionLocal() as s:
        stmt = select(BroadcastJob).where(
            BroadcastJob.status == "pending",
            BroadcastJob.scheduled_at.is_not(None),
            BroadcastJob.scheduled_at <= now,
        )
        rows = (await s.execute(stmt)).scalars().all()

    if not rows or not _bot_app:
        return
    for job in rows:
        log.info("调度器触发群发 #%s", job.id)
        try:
            await execute_job_id(_bot_app, job.id)
        except Exception:  # noqa: BLE001
            log.exception("定时群发 #%s 失败", job.id)


async def expire_subscriptions() -> None:
    now = datetime.utcnow()
    async with SessionLocal() as s:
        stmt = select(Subscription).where(
            Subscription.status == "active",
            Subscription.expires_at <= now,
        )
        rows = (await s.execute(stmt)).scalars().all()
        for sub in rows:
            sub.status = "expired"
        if rows:
            await s.commit()
            log.info("订阅过期：%d 个", len(rows))


async def run_recurring_entries() -> None:
    """每小时检查一次：把到点的循环条目写入流水。"""
    from datetime import timedelta

    now = datetime.utcnow()
    async with SessionLocal() as s:
        stmt = select(RecurringEntry).where(
            RecurringEntry.enabled.is_(True),
            (RecurringEntry.next_run.is_(None)) | (RecurringEntry.next_run <= now),
        )
        rows = (await s.execute(stmt)).scalars().all()
        for r in rows:
            s.add(
                LedgerEntry(
                    account_id=r.account_id,
                    kind=r.kind,
                    amount=r.amount,
                    category=r.category,
                    note=(r.note or "") + " [定期]",
                )
            )
            r.next_run = now + timedelta(days=30)  # 简化：默认按月
        if rows:
            await s.commit()
            log.info("定期入账：%d 条", len(rows))


async def cleanup_captcha() -> None:
    """超时未通过验证 → 踢出。"""
    if not _bot_app:
        return
    now = datetime.utcnow()
    async with SessionLocal() as s:
        stmt = select(CaptchaSession).where(CaptchaSession.expires_at <= now)
        rows = (await s.execute(stmt)).scalars().all()
        for sess in rows:
            try:
                await _bot_app.bot.ban_chat_member(
                    chat_id=sess.chat_id,
                    user_id=sess.user_id,
                    until_date=int(datetime.utcnow().timestamp()) + 60,
                )
                await _bot_app.bot.unban_chat_member(sess.chat_id, sess.user_id)
                if sess.message_id:
                    try:
                        await _bot_app.bot.delete_message(sess.chat_id, sess.message_id)
                    except Exception:
                        pass
            except Exception:  # noqa: BLE001
                log.warning("验证超时踢出失败 chat=%s user=%s", sess.chat_id, sess.user_id)
            await s.delete(sess)
        if rows:
            await s.commit()


def setup_jobs() -> None:
    scheduler.add_job(
        run_due_broadcasts, IntervalTrigger(seconds=30), id="broadcasts", replace_existing=True
    )
    scheduler.add_job(
        expire_subscriptions, CronTrigger(minute=5), id="sub_expire", replace_existing=True
    )
    scheduler.add_job(
        run_recurring_entries, CronTrigger(minute=10), id="recurring", replace_existing=True
    )
    scheduler.add_job(
        cleanup_captcha, IntervalTrigger(seconds=20), id="captcha", replace_existing=True
    )
