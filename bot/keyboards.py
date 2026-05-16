"""集中管理 InlineKeyboard / ReplyKeyboard。"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("📒 记账", callback_data="menu:ledger"),
            InlineKeyboardButton("💬 自动回复", callback_data="menu:autoreply"),
        ],
        [
            InlineKeyboardButton("📊 统计报表", callback_data="menu:stats"),
            InlineKeyboardButton("ℹ️ 帮助", callback_data="menu:help"),
        ],
    ]
    if is_admin:
        rows.append(
            [
                InlineKeyboardButton("📡 搬运规则", callback_data="menu:forward"),
                InlineKeyboardButton("📣 群发中心", callback_data="menu:broadcast"),
            ]
        )
        rows.append(
            [InlineKeyboardButton("⚙️ 管理面板", callback_data="menu:admin")]
        )
    return InlineKeyboardMarkup(rows)


def ledger_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ 收入", callback_data="ledger:add:income"),
                InlineKeyboardButton("➖ 支出", callback_data="ledger:add:expense"),
            ],
            [
                InlineKeyboardButton("📋 今日明细", callback_data="ledger:list:today"),
                InlineKeyboardButton("📅 本月汇总", callback_data="ledger:report:month"),
            ],
            [
                InlineKeyboardButton("🗂 账户管理", callback_data="ledger:accounts"),
                InlineKeyboardButton("📈 走势图", callback_data="ledger:chart"),
            ],
            [InlineKeyboardButton("« 返回", callback_data="menu:home")],
        ]
    )


def back_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("« 返回主菜单", callback_data="menu:home")]]
    )


def confirm(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ 确认", callback_data=f"confirm:{action}"),
                InlineKeyboardButton("❌ 取消", callback_data="confirm:cancel"),
            ]
        ]
    )
