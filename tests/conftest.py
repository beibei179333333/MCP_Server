"""测试夹具：stub telethon、隔离数据库。"""
from __future__ import annotations

import os
import sys
import types
import asyncio
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _stub_telethon():
    if "telethon" in sys.modules:
        return
    fake = types.ModuleType("telethon")
    fake.TelegramClient = type("TelegramClient", (), {})
    sys.modules["telethon"] = fake
    events = types.ModuleType("telethon.events")
    events.NewMessage = lambda *a, **kw: None
    sys.modules["telethon.events"] = events
    errors = types.ModuleType("telethon.errors")
    errors.FloodWaitError = type("FloodWaitError", (Exception,), {"seconds": 0})
    sys.modules["telethon.errors"] = errors
    types_mod = types.ModuleType("telethon.tl.types")
    types_mod.DocumentAttributeFilename = type("DocumentAttributeFilename", (), {})
    types_mod.MessageMediaDocument = type("MessageMediaDocument", (), {})
    types_mod.MessageMediaPhoto = type("MessageMediaPhoto", (), {})
    sys.modules["telethon.tl"] = types.ModuleType("telethon.tl")
    sys.modules["telethon.tl.types"] = types_mod


_stub_telethon()
os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("WEB_ENABLED", "false")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db():
    from bot.database import init_db, SessionLocal
    await init_db()
    yield SessionLocal
