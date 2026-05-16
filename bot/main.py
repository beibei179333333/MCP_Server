"""主入口：组装 Application、注册 handler、并行启动 user-bot。"""
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
from .handlers import admin, autoreply, broadcast, common, forward_admin, ledger, router
from .logger import setup_logging
from .userbot import manager as forward_manager, start_userbot


async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log = logging.getLogger("bot.error")
    log.exception("处理更新出错: %s", context.error)


def build_application() -> Application:
    app = ApplicationBuilder().token(settings.bot_token).build()

    # 基础
    app.add_handler(CommandHandler(["start", "menu"], common.start))
    app.add_handler(CommandHandler("help", common.help_cmd))
    app.add_handler(CommandHandler("id", common.show_id))
    app.add_handler(CommandHandler("cancel", common.cancel))

    # 记账
    app.add_handler(CommandHandler("ledger", ledger.ledger_cmd))
    app.add_handler(CommandHandler("today", ledger.today_cmd))
    app.add_handler(CommandHandler("month", ledger.month_cmd))
    app.add_handler(CommandHandler("chart", ledger.chart_cmd))
    app.add_handler(CommandHandler("export", ledger.export_cmd))

    # 自动回复
    app.add_handler(CommandHandler("ar_add", autoreply.add_cmd))
    app.add_handler(CommandHandler("ar_add_re", autoreply.add_re_cmd))
    app.add_handler(CommandHandler("ar_list", autoreply.list_cmd))
    app.add_handler(CommandHandler("ar_del", autoreply.del_cmd))
    app.add_handler(CommandHandler("ar_toggle", autoreply.toggle_cmd))

    # 管理员
    app.add_handler(CommandHandler("admin", admin.admin_cmd))
    app.add_handler(CommandHandler("stats", admin.stats_cmd))
    app.add_handler(CommandHandler("users", admin.users_cmd))
    app.add_handler(CommandHandler("chats", admin.chats_cmd))

    # 搬运规则
    app.add_handler(CommandHandler("fw_add", forward_admin.add_cmd))
    app.add_handler(CommandHandler("fw_list", forward_admin.list_cmd))
    app.add_handler(CommandHandler("fw_del", forward_admin.del_cmd))
    app.add_handler(CommandHandler("fw_toggle", forward_admin.toggle_cmd))
    app.add_handler(CommandHandler("fw_filter", forward_admin.filter_cmd))
    app.add_handler(CommandHandler("fw_replace", forward_admin.replace_cmd))

    async def fw_reload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from .utils import is_admin
        if not is_admin(update.effective_user.id):
            await update.effective_message.reply_text("⛔ 仅管理员可用")
            return
        forward_manager.request_reload()
        await update.effective_message.reply_text("🔁 已请求 user-bot 重新加载规则")
    app.add_handler(CommandHandler("fw_reload", fw_reload))

    # 群发
    app.add_handler(CommandHandler("broadcast", broadcast.broadcast_cmd))

    # 回调
    app.add_handler(CallbackQueryHandler(common.menu_callback, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(ledger.ledger_callback, pattern=r"^ledger:"))
    app.add_handler(CallbackQueryHandler(broadcast.broadcast_callback, pattern=r"^bc:"))
    app.add_handler(CallbackQueryHandler(admin.admin_callback, pattern=r"^admin:"))

    # chat 成员变更追踪
    app.add_handler(
        ChatMemberHandler(admin.track_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER)
    )

    # 文本兜底：路由到 ledger / autoreply / broadcast flow
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.Document.ALL | filters.VIDEO) & ~filters.COMMAND,
            router.text_router,
        )
    )

    app.add_error_handler(_error_handler)
    return app


async def _run() -> None:
    log = setup_logging()

    missing = settings.validate()
    if missing:
        log.error("缺少必要配置：%s。请复制 .env.example 为 .env 并填写。", ", ".join(missing))
        return

    await init_db()
    log.info("数据库已初始化：%s", settings.database_url)

    app = build_application()

    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    log.info("Bot 已启动（@%s）", (await app.bot.get_me()).username)

    userbot_task = asyncio.create_task(start_userbot())

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
        userbot_task.cancel()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
