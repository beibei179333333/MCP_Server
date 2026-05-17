"""主入口：组装 Application + 调度器 + user-bot + Web 面板。"""
from __future__ import annotations

import asyncio
import logging
import signal

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import settings
from .database import init_db
from .handlers import (
    admin, autoreply, backup, broadcast, common, forward_admin, fw_editor,
    group, ledger, referral, router, subscription,
)
from .logger import setup_logging
from .scheduler import scheduler, set_bot_app, setup_jobs
from .userbot import manager as forward_manager, set_bot_app as set_userbot_app, start_userbot
from .web.app import start_web


async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log = logging.getLogger("bot.error")
    log.exception("更新处理失败: %s", context.error)
    # 给用户回一条友好提示（不暴露异常细节）
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ 出了点小问题，已经记到日志里。可以 /menu 重试，"
                "或联系管理员（/id 查看身份信息一起报告）。"
            )
    except Exception:
        pass


def build_application() -> Application:
    app = ApplicationBuilder().token(settings.bot_token).build()

    # ---- 基础 ----
    app.add_handler(CommandHandler(["start", "menu"], common.start))
    app.add_handler(CommandHandler("help", common.help_cmd))
    app.add_handler(CommandHandler("id", common.show_id))
    app.add_handler(CommandHandler("cancel", common.cancel))

    # ---- 记账 ----
    app.add_handler(CommandHandler("ledger", ledger.ledger_cmd))
    app.add_handler(CommandHandler("today", ledger.today_cmd))
    app.add_handler(CommandHandler("month", ledger.month_cmd))
    app.add_handler(CommandHandler("chart", ledger.chart_cmd))
    app.add_handler(CommandHandler("export", ledger.export_cmd))
    app.add_handler(CommandHandler("budget", ledger.budget_set_cmd))
    app.add_handler(CommandHandler("budgets", ledger.budget_list_cmd))

    # ---- 自动回复 ----
    app.add_handler(CommandHandler("ar_add", autoreply.add_cmd))
    app.add_handler(CommandHandler("ar_add_re", autoreply.add_re_cmd))
    app.add_handler(CommandHandler("ar_list", autoreply.list_cmd))
    app.add_handler(CommandHandler("ar_del", autoreply.del_cmd))
    app.add_handler(CommandHandler("ar_toggle", autoreply.toggle_cmd))

    # ---- 管理员 ----
    app.add_handler(CommandHandler("admin", admin.admin_cmd))
    app.add_handler(CommandHandler("stats", admin.stats_cmd))
    app.add_handler(CommandHandler("users", admin.users_cmd))
    app.add_handler(CommandHandler("chats", admin.chats_cmd))
    app.add_handler(CommandHandler("backup", backup.backup_cmd))
    app.add_handler(CommandHandler("backups", backup.backups_list))

    # ---- 搬运规则 ----
    app.add_handler(CommandHandler("fw_add", forward_admin.add_cmd))
    app.add_handler(CommandHandler("fw_list", forward_admin.list_cmd))
    app.add_handler(CommandHandler("fw_del", forward_admin.del_cmd))
    app.add_handler(CommandHandler("fw_toggle", forward_admin.toggle_cmd))
    app.add_handler(CommandHandler("fw_filter", forward_admin.filter_cmd))
    app.add_handler(CommandHandler("fw_replace", forward_admin.replace_cmd))
    app.add_handler(CommandHandler("fw_caption", forward_admin.caption_cmd))
    app.add_handler(CommandHandler("fw_format", forward_admin.format_cmd))
    app.add_handler(CommandHandler("fw_media", forward_admin.media_cmd))
    app.add_handler(CommandHandler("fw_watermark", forward_admin.watermark_cmd))
    app.add_handler(CommandHandler("fw_plugins", forward_admin.plugins_show))
    app.add_handler(CommandHandler("fw_backfill", forward_admin.backfill_cmd))
    app.add_handler(CommandHandler("fw_preview", forward_admin.preview_cmd))
    app.add_handler(CommandHandler("qf", forward_admin.quick_forward_cmd))
    app.add_handler(CommandHandler("fw_chain", forward_admin.chain_cmd))
    app.add_handler(CommandHandler("fw_sender", forward_admin.sender_cmd))
    app.add_handler(CommandHandler("fw_topic", forward_admin.topic_cmd))
    app.add_handler(CommandHandler("fw_folder", forward_admin.folder_cmd))
    app.add_handler(CommandHandler("fw_folders", forward_admin.folders_cmd))
    app.add_handler(CommandHandler("fw_sync", forward_admin.sync_cmd))
    app.add_handler(CommandHandler("fw_buttons", forward_admin.buttons_cmd))
    app.add_handler(CommandHandler("fw_ai", forward_admin.ai_cmd))

    # ---- 推广 / 返佣 ----
    app.add_handler(CommandHandler("myref", referral.myref_cmd))
    app.add_handler(CommandHandler("withdraw", referral.withdraw_cmd))
    app.add_handler(CommandHandler("toplist", referral.toplist_cmd))
    app.add_handler(CommandHandler("wd_approve", referral.wd_approve))
    app.add_handler(CommandHandler("wd_reject", referral.wd_reject))

    # ---- AI ----
    app.add_handler(CommandHandler("ai", common.ai_query_cmd))

    async def fw_reload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from .utils import is_admin
        if not is_admin(update.effective_user.id):
            await update.effective_message.reply_text("⛔ 仅管理员可用")
            return
        forward_manager.request_reload()
        await update.effective_message.reply_text("🔁 已通知 user-bot 重载规则")
    app.add_handler(CommandHandler("fw_reload", fw_reload))

    # ---- 群发 ----
    app.add_handler(CommandHandler("broadcast", broadcast.broadcast_cmd))

    # ---- 订阅 ----
    app.add_handler(CommandHandler("plans", subscription.plans_cmd))
    app.add_handler(CommandHandler("mysub", subscription.my_sub_cmd))
    app.add_handler(CommandHandler("grant_sub", subscription.grant_sub_cmd))
    app.add_handler(CommandHandler("payments", subscription.payments_cmd))

    # ---- 群组功能 ----
    app.add_handler(CommandHandler("welcome", group.welcome_set))
    app.add_handler(CommandHandler("welcome_off", group.welcome_off))
    app.add_handler(CommandHandler("captcha", group.captcha_toggle))
    app.add_handler(CommandHandler("antispam", group.antispam_toggle))

    # ---- 回调（按模式分发） ----
    app.add_handler(CallbackQueryHandler(common.menu_callback, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(common.help_callback, pattern=r"^help:"))
    app.add_handler(CallbackQueryHandler(ledger.ledger_callback, pattern=r"^ledger:"))
    app.add_handler(CallbackQueryHandler(broadcast.broadcast_callback, pattern=r"^bc:"))
    app.add_handler(CallbackQueryHandler(admin.admin_callback, pattern=r"^admin:"))
    app.add_handler(CallbackQueryHandler(subscription.subscription_callback, pattern=r"^sub:"))
    app.add_handler(CallbackQueryHandler(group.captcha_callback, pattern=r"^cap:"))
    app.add_handler(CallbackQueryHandler(admin.pager_callback, pattern=r"^(ulist|clist|fwlist):"))
    app.add_handler(CallbackQueryHandler(fw_editor.editor_callback, pattern=r"^fwed:"))
    app.add_handler(CallbackQueryHandler(fw_editor.wizard_skip_callback, pattern=r"^fwwz:"))
    app.add_handler(CallbackQueryHandler(autoreply.ar_callback, pattern=r"^ar:"))

    # ---- chat 状态追踪 ----
    app.add_handler(
        ChatMemberHandler(admin.track_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER)
    )
    app.add_handler(
        ChatMemberHandler(group.on_chat_member, ChatMemberHandler.CHAT_MEMBER)
    )

    # ---- 文本兜底 ----
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.Document.ALL | filters.VIDEO)
            & ~filters.COMMAND,
            router.text_router,
        )
    )

    app.add_error_handler(_error_handler)
    return app


async def _run() -> None:
    log = setup_logging()

    missing = settings.validate()
    if missing:
        log.error("缺少必要配置：%s。请复制 .env.example → .env 并填写。", ", ".join(missing))
        return

    await init_db()
    log.info("数据库已初始化：%s", settings.database_url)

    app = build_application()
    set_bot_app(app)
    set_userbot_app(app)
    setup_jobs()

    await app.initialize()
    await app.start()
    await app.updater.start_polling(
        allowed_updates=Update.ALL_TYPES, drop_pending_updates=True
    )
    me = await app.bot.get_me()
    log.info("Bot 已启动: @%s", me.username)

    # 启动通告：通知所有管理员机器人已就绪 + 附带 Web 控制台凭据
    web_line = ""
    if settings.web_enabled:
        web_line = (
            f"\n\n🖥 *Web 控制台*\n"
            f"地址：`http://<server>:{settings.web_port}`\n"
            f"账号：`{settings.web_username}`\n"
            f"密码：`{settings.effective_web_password}`"
        )
    ready_msg = (
        f"✅ *我已经准备好了，可以工作！*\n"
        f"机器人 @{me.username} 已成功上线 🚀\n\n"
        f"📚 发送 /help 查看命令\n"
        f"🏠 发送 /menu 打开图形菜单"
        f"{web_line}"
    )
    if not settings.admin_ids:
        log.warning("ADMIN_IDS 未配置，启动通告仅记录到日志")
        log.info(ready_msg)
    else:
        for admin_id in settings.admin_ids:
            try:
                await app.bot.send_message(
                    admin_id, ready_msg, parse_mode="Markdown"
                )
                log.info("已向管理员 %s 发送启动通告", admin_id)
            except Exception as e:
                log.warning("向 %s 发送启动通告失败: %s", admin_id, e)

    scheduler.start()
    log.info("调度器已启动（broadcasts/sub_expire/recurring/captcha）")

    background_tasks: list[asyncio.Task] = []
    if settings.userbot_enabled:
        background_tasks.append(asyncio.create_task(start_userbot()))
    if settings.web_enabled:
        background_tasks.append(asyncio.create_task(start_web()))

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    try:
        await stop_event.wait()
    finally:
        log.info("正在停止…")
        scheduler.shutdown(wait=False)
        for t in background_tasks:
            t.cancel()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
