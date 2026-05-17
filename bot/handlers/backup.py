"""备份 / 还原：SQLite 安全备份 + 保留策略。"""
from __future__ import annotations

import gzip
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from ..config import BASE_DIR, DATA_DIR, settings
from ..utils import admin_only, fmt_size

log = logging.getLogger(__name__)
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def _db_path() -> Path | None:
    """从 DATABASE_URL 解析出 SQLite 文件路径。Postgres/MySQL 返回 None。"""
    url = settings.database_url
    if not url.startswith("sqlite"):
        return None
    # sqlite+aiosqlite:///./data/bot.db  或  sqlite:////abs/path
    body = url.split("///", 1)[-1]
    p = Path(body)
    if not p.is_absolute():
        p = BASE_DIR / p
    return p


def _backup_once() -> Path | None:
    """同步做一次 SQLite 备份；同时清掉过老的备份。"""
    src = _db_path()
    if not src or not src.exists():
        log.warning("备份跳过：DB 不是 SQLite 或文件不存在")
        return None
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out = BACKUP_DIR / f"bot-{stamp}.db.gz"
    # SQLite 的 .db 文件直接 cp 不一定安全（事务中），但 aiosqlite 默认 WAL 模式下
    # 文件级复制可接受；更稳的做法是 sqlite3 .backup API。
    try:
        import sqlite3
        tmp_path = BACKUP_DIR / f".tmp-{stamp}.db"
        src_conn = sqlite3.connect(str(src))
        dst_conn = sqlite3.connect(str(tmp_path))
        with dst_conn:
            src_conn.backup(dst_conn)
        src_conn.close()
        dst_conn.close()
        with open(tmp_path, "rb") as r, gzip.open(out, "wb", compresslevel=6) as w:
            shutil.copyfileobj(r, w)
        tmp_path.unlink(missing_ok=True)
    except Exception as e:  # noqa: BLE001
        log.exception("备份失败: %s", e)
        return None

    # 保留 7 天
    cutoff = datetime.utcnow() - timedelta(days=7)
    for f in BACKUP_DIR.glob("bot-*.db.gz"):
        if datetime.utcfromtimestamp(f.stat().st_mtime) < cutoff:
            try:
                f.unlink()
            except Exception:  # noqa: BLE001
                pass
    log.info("备份完成：%s (%s)", out.name, fmt_size(out.stat().st_size))
    return out


async def run_backup() -> Path | None:
    """供调度器调用。"""
    import asyncio
    return await asyncio.to_thread(_backup_once)


@admin_only
async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await update.effective_message.reply_text("⏳ 正在备份…")
    out = await run_backup()
    if not out:
        await msg.edit_text("❌ 备份失败（看日志）")
        return
    await msg.edit_text(
        f"✅ 备份完成\n`{out.name}` ({fmt_size(out.stat().st_size)})\n位于 `{BACKUP_DIR}`",
        parse_mode="Markdown",
    )
    try:
        await update.effective_message.reply_document(
            document=open(out, "rb"),
            filename=out.name,
            caption=f"📦 {out.name}",
        )
    except Exception as e:  # noqa: BLE001
        log.warning("发送备份文件失败: %s", e)


@admin_only
async def backups_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    files = sorted(BACKUP_DIR.glob("bot-*.db.gz"), reverse=True)[:20]
    if not files:
        await update.effective_message.reply_text("📭 暂无备份")
        return
    lines = ["📦 *最近 20 个备份*\n"]
    for f in files:
        ts = datetime.utcfromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        lines.append(f"• `{f.name}` · {fmt_size(f.stat().st_size)} · {ts}")
    await update.effective_message.reply_text(
        "\n".join(lines), parse_mode="Markdown"
    )
