"""基础命令：/start /help /menu /id 等。"""
from __future__ import annotations

import logging
from datetime import datetime

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ..keyboards import back_home, main_menu
from ..utils import display_name, is_admin, upsert_user

log = logging.getLogger(__name__)

WELCOME = """\
👋 *欢迎使用多功能助手机器人*

我能帮你做这些事：
• 📡 *自动搬运* — 把指定频道/群组的消息实时转发到你的目标群
• 📒 *记账助手* — 私聊一句 `120 餐饮 午餐` 即可记账，支持图表
• 📣 *群发中心* — 一键群发到所有订阅用户 / 关联群组
• 💬 *自动回复* — 关键词命中即自动答复，可分群配置
• 📊 *数据报表* — 月度收支、群发明细、规则统计一目了然

点击下方按钮开始使用 👇
"""

HELP = """\
*可用命令*

通用：
/start /menu — 主菜单
/id — 查看当前 chat 和 user id
/cancel — 取消当前操作

记账（私聊）：
直接发 `金额 类别 备注`，如 `120 餐饮 午餐`、`-50 打车`
/ledger — 打开记账面板
/today /month — 今日/本月汇总
/chart — 收支走势图
/export — 导出 CSV

自动回复：
/ar\\_add 关键词 ::: 回复内容
/ar\\_list — 列出本群规则
/ar\\_del <id> — 删除规则

管理员：
/admin — 管理面板
/fw\\_add 源 目标 [名字] — 添加搬运规则
/fw\\_list /fw\\_del <id> /fw\\_toggle <id>
/broadcast — 进入群发流程
/stats — 全局统计
/users /chats — 查看用户 / 群组列表
"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await upsert_user(update)
    user = update.effective_user
    is_a = bool(user and is_admin(user.id))
    await update.effective_message.reply_text(
        WELCOME, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu(is_a)
    )


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await upsert_user(update)
    user = update.effective_user
    is_a = bool(user and is_admin(user.id))
    await update.effective_message.reply_text(
        "🏠 *主菜单*", parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu(is_a)
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        HELP, parse_mode=ParseMode.MARKDOWN, reply_markup=back_home()
    )


async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    text = (
        f"🪪 *身份信息*\n"
        f"• 用户：{display_name(user)}\n"
        f"• User ID：`{user.id}`\n"
        f"• Chat ID：`{chat.id}` ({chat.type})\n"
        f"• 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("flow", None)
    await update.effective_message.reply_text("✅ 已取消当前操作", reply_markup=main_menu(is_admin(update.effective_user.id)))


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理主菜单 InlineKeyboard。"""
    query = update.callback_query
    await query.answer()
    target = query.data.split(":", 1)[1]
    user = update.effective_user
    is_a = is_admin(user.id)

    if target == "home":
        await query.edit_message_text(
            "🏠 *主菜单*", parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu(is_a)
        )
    elif target == "help":
        await query.edit_message_text(
            HELP, parse_mode=ParseMode.MARKDOWN, reply_markup=back_home()
        )
    elif target == "ledger":
        from .ledger import open_ledger_panel
        await open_ledger_panel(update, context)
    elif target == "autoreply":
        from .autoreply import open_autoreply_panel
        await open_autoreply_panel(update, context)
    elif target == "stats":
        from .admin import show_stats
        await show_stats(update, context)
    elif target == "forward" and is_a:
        from .forward_admin import open_forward_panel
        await open_forward_panel(update, context)
    elif target == "broadcast" and is_a:
        from .broadcast import open_broadcast_panel
        await open_broadcast_panel(update, context)
    elif target == "admin" and is_a:
        from .admin import open_admin_panel
        await open_admin_panel(update, context)
    else:
        await query.edit_message_text("⛔ 无权限或未知菜单", reply_markup=back_home())
