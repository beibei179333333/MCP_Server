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
*命令参考*

🔹 *通用*
/start /menu — 主菜单
/id — 查看当前 chat / user id
/cancel — 取消当前操作

🔹 *记账*（私聊）
直接发 `金额 类别 备注`，如 `120 餐饮 午餐`、`-50 打车`
/ledger /today /month /chart /export
/budget 类别 金额 — 设置月预算
/budgets — 查看预算执行

🔹 *自动回复*
`/ar_add 关键词 ::: 回复内容`
`/ar_add_re 正则 ::: 内容`
/ar_list  /ar_toggle <id>  /ar_del <id>

🔹 *订阅*
/plans — 查看套餐
/mysub — 我的订阅

🔹 *群组*（群管理员）
/welcome <文本>  /welcome_off
/captcha — 切换入群验证
/antispam — 切换反垃圾

🔹 *管理员*
/admin /stats /users /chats /payments
/grant\\_sub <user_id> <plan>

🔹 *搬运（仅管理员）*
/fw\\_add 源 目标[,目标2] [名字]
/fw\\_filter <id> kw=A,B bl=C
/fw\\_replace <id> 原文 => 新文
/fw\\_caption <id> header=🔥 | footer=—@CH
/fw\\_format <id> links=1 mentions=1 emoji=0
/fw\\_media <id> allow=photo,video,text
/fw\\_watermark <id> @MyChannel
/fw\\_backfill <id> 200 — 历史回填
/fw\\_list /fw\\_toggle /fw\\_del /fw\\_reload

🔹 *群发（仅管理员）*
/broadcast — 面板
/broadcast users 内容
/broadcast tag VIP 内容
消息可附加：`@schedule 2030-01-01 10:00` 定时
消息可附加：`@buttons [["按钮","https://..."]]`

🔹 *Web 后台*
默认 http://server:8000
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
    elif target == "subscription":
        from .subscription import plans_cmd
        await plans_cmd(update, context)
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
