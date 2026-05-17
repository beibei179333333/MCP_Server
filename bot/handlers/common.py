"""基础命令：/start /help /menu /id 等。"""
from __future__ import annotations

import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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

新手提示：
• 私聊我直接发数字（如 `100 餐饮`）= 记账
• 群里把我设为管理员才能用全部群功能
• 发 /help 看完整命令、/menu 看图形菜单
"""


HELP_INDEX = (
    "📚 *命令帮助* — 按主题点按钮查看\n"
    "（或发 /menu 进图形菜单）"
)

HELP_TOPICS = {
    "common": (
        "🔹 *通用命令*\n\n"
        "/start /menu — 主菜单\n"
        "/help — 本帮助\n"
        "/id — 查看 chat / user id\n"
        "/cancel — 取消当前操作"
    ),
    "ledger": (
        "🔹 *记账*\n\n"
        "直接发：`金额 类别 备注`\n"
        "例：`120 餐饮 午餐`、`+5000 工资`、`-50 打车`\n\n"
        "/ledger — 面板\n"
        "/today /month — 今日 / 本月汇总\n"
        "/chart — 近 30 天走势图\n"
        "/export — 导出 CSV\n"
        "/budget 类别 金额 — 设月预算\n"
        "/budgets — 查看执行"
    ),
    "autoreply": (
        "🔹 *自动回复*\n\n"
        "`/ar_add 关键词 ::: 回复内容`\n"
        "`/ar_add_re ^正则$ ::: 回复内容`\n"
        "/ar_list /ar_toggle <id> /ar_del <id>"
    ),
    "broadcast": (
        "🔹 *群发*（管理员）\n\n"
        "/broadcast — 进入面板\n"
        "/broadcast users 内容\n"
        "/broadcast chats — 回复一条消息后执行\n"
        "/broadcast both 内容\n"
        "/broadcast tag VIP 内容 — 按标签分群\n\n"
        "*消息元指令*：\n"
        "  `@schedule 2030-01-01 10:00` 定时\n"
        "  `@buttons [[\"标签\",\"https://...\"]]` 内联按钮"
    ),
    "forward": (
        "🔹 *搬运*（管理员）\n\n"
        "*一键创建*：\n"
        "  `/qf 源 目标 黑名单A,黑名单B`\n\n"
        "*详细*：\n"
        "  /fw_add 源 目标[,目标2] [名字]\n"
        "  /fw_filter <id> kw=A,B bl=C,D\n"
        "  /fw_replace <id> 原文 => 新文\n"
        "  /fw_caption <id> header=🔥 | footer=—@CH\n"
        "  /fw_format <id> links=1 mentions=1 emoji=0\n"
        "  /fw_media <id> allow=photo,video,text\n"
        "  /fw_watermark <id> @MyChannel\n"
        "  /fw_backfill <id> 200 — 历史回填\n"
        "  /fw_preview <id> 样本文本 — 试丢/转\n"
        "  /fw_list /fw_toggle /fw_del /fw_reload"
    ),
    "group": (
        "🔹 *群组管理*（群管理员）\n\n"
        "/welcome <欢迎语> — 占位符 `{name}` `{username}` `{chat}`\n"
        "/welcome_off — 关闭\n"
        "/captcha — 切换入群验证\n"
        "/antispam — 切换反垃圾"
    ),
    "sub": (
        "🔹 *订阅*\n\n"
        "/plans — 查看套餐\n"
        "/mysub — 我的订阅\n\n"
        "*管理员*：\n"
        "/grant_sub <user_id> <plan_code> — 手动开通\n"
        "/payments — 订单列表"
    ),
    "admin": (
        "🔹 *管理员*\n\n"
        "/admin — 管理面板\n"
        "/stats — 全局统计\n"
        "/users — 用户列表（分页）\n"
        "/chats — 群组列表（分页）\n"
        "/backup — 立即备份\n"
        "/backups — 备份列表"
    ),
}


def _help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📘 通用", callback_data="help:common"),
             InlineKeyboardButton("📒 记账", callback_data="help:ledger")],
            [InlineKeyboardButton("💬 自动回复", callback_data="help:autoreply"),
             InlineKeyboardButton("📣 群发", callback_data="help:broadcast")],
            [InlineKeyboardButton("📡 搬运", callback_data="help:forward"),
             InlineKeyboardButton("👋 群组", callback_data="help:group")],
            [InlineKeyboardButton("💎 订阅", callback_data="help:sub"),
             InlineKeyboardButton("⚙️ 管理员", callback_data="help:admin")],
            [InlineKeyboardButton("« 返回主菜单", callback_data="menu:home")],
        ]
    )


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
        HELP_INDEX, parse_mode=ParseMode.MARKDOWN, reply_markup=_help_keyboard()
    )


async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":", 1)
    if len(parts) < 2:
        return
    topic = parts[1]
    if topic == "back":
        await query.edit_message_text(
            HELP_INDEX, parse_mode=ParseMode.MARKDOWN, reply_markup=_help_keyboard()
        )
        return
    body = HELP_TOPICS.get(topic, "未知主题")
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("« 主题列表", callback_data="help:back"),
          InlineKeyboardButton("🏠 主菜单", callback_data="menu:home")]]
    )
    try:
        await query.edit_message_text(body, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    except Exception:
        pass


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
            HELP_INDEX, parse_mode=ParseMode.MARKDOWN, reply_markup=_help_keyboard()
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
