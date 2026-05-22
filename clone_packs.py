"""
批量克隆 Telegram 表情包并统一重命名。

流程(对 packs.txt 里的每一个原始链接):
  1. /cancel               # 重置 bot 状态
  2. /cloneemojipack 或 /clonepack   # 视 addemoji / addstickers 而定
  3. 等 bot 提示后,发送原始 t.me/addemoji/... 链接
  4. 等 bot 提示后,发送新的 short_name(emojipd_001 ~ emojipd_097)
  5. 等 bot 提示后,发送新的 title(会员表情🔥 @emojipd)
  6. 抓取 bot 返回的新链接,记录到 state.json

进度持久化在 state.json,中途断了重跑会从下一个未完成的包继续。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.custom import Message

load_dotenv()

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
PHONE = os.environ.get("TG_PHONE")
SESSION = os.environ.get("TG_SESSION", "clone_session")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "fStikBot")
NEW_TITLE = os.environ.get("NEW_TITLE", "会员表情🔥 @emojipd")
SHORT_PREFIX = os.environ.get("SHORT_PREFIX", "emojipd")
START_INDEX = int(os.environ.get("START_INDEX", "1"))
STEP_DELAY = float(os.environ.get("STEP_DELAY", "3"))
PACK_DELAY = float(os.environ.get("PACK_DELAY", "8"))

ROOT = Path(__file__).parent
PACKS_FILE = ROOT / "packs.txt"
STATE_FILE = ROOT / "state.json"

REPLY_TIMEOUT = 30  # 单条 bot 回复最长等待秒数


@dataclass
class PackResult:
    index: int
    source_url: str
    new_short_name: str
    new_title: str
    new_url: Optional[str] = None
    status: str = "pending"  # pending | done | failed
    error: Optional[str] = None


@dataclass
class State:
    results: list[PackResult] = field(default_factory=list)

    @classmethod
    def load(cls) -> "State":
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text())
            return cls(results=[PackResult(**r) for r in data["results"]])
        return cls()

    def save(self) -> None:
        STATE_FILE.write_text(
            json.dumps(
                {"results": [asdict(r) for r in self.results]},
                ensure_ascii=False,
                indent=2,
            )
        )


def load_sources() -> list[str]:
    urls: list[str] = []
    for line in PACKS_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def is_emoji_pack(url: str) -> bool:
    return "/addemoji/" in url


async def wait_reply(client: TelegramClient, bot, after_id: int) -> Message:
    """等 bot 发新消息(id > after_id),最多 REPLY_TIMEOUT 秒。"""
    deadline = asyncio.get_event_loop().time() + REPLY_TIMEOUT
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(1.0)
        msgs = await client.get_messages(bot, limit=1)
        if msgs and msgs[0].id > after_id and msgs[0].sender_id != (await client.get_me()).id:
            return msgs[0]
    raise TimeoutError(f"bot 在 {REPLY_TIMEOUT}s 内没有回复")


async def send_and_wait(client: TelegramClient, bot, text: str) -> Message:
    """发一条消息,等到一条新的 bot 回复。"""
    sent = await client.send_message(bot, text)
    await asyncio.sleep(STEP_DELAY)
    return await wait_reply(client, bot, sent.id)


NEW_LINK_RE = re.compile(r"https?://t\.me/add(?:emoji|stickers)/[\w_]+")


def extract_new_link(text: str) -> Optional[str]:
    if not text:
        return None
    m = NEW_LINK_RE.search(text)
    return m.group(0) if m else None


async def clone_one(
    client: TelegramClient,
    bot,
    item: PackResult,
) -> None:
    print(f"\n=== [{item.index:03d}/{len(item_total_holder)}] {item.source_url} ===")
    # 1. cancel 任何残留状态
    try:
        await client.send_message(bot, "/cancel")
        await asyncio.sleep(STEP_DELAY)
    except FloodWaitError as e:
        print(f"FloodWait {e.seconds}s, sleeping...")
        await asyncio.sleep(e.seconds + 1)

    # 2. 开始克隆
    start_cmd = "/cloneemojipack" if is_emoji_pack(item.source_url) else "/clonepack"
    reply = await send_and_wait(client, bot, start_cmd)
    print(f"<bot> {(reply.message or '')[:120]!r}")

    # 3. 发送原 pack 链接
    reply = await send_and_wait(client, bot, item.source_url)
    print(f"<bot> {(reply.message or '')[:120]!r}")

    # 4. 发送新的 short_name
    reply = await send_and_wait(client, bot, item.new_short_name)
    print(f"<bot> {(reply.message or '')[:120]!r}")

    # 5. 发送新的 title
    reply = await send_and_wait(client, bot, item.new_title)
    print(f"<bot> {(reply.message or '')[:160]!r}")

    # 6. 等待最终带链接的回复(有时分几条)
    new_link = extract_new_link(reply.message or "")
    deadline = asyncio.get_event_loop().time() + REPLY_TIMEOUT
    last_id = reply.id
    while new_link is None and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(2)
        try:
            extra = await wait_reply(client, bot, last_id)
        except TimeoutError:
            break
        last_id = extra.id
        print(f"<bot> {(extra.message or '')[:160]!r}")
        new_link = extract_new_link(extra.message or "")

    if not new_link:
        item.status = "failed"
        item.error = "未能在 bot 回复中找到新链接"
        print(f"!! 失败: {item.error}")
        return

    item.new_url = new_link
    item.status = "done"
    print(f"OK -> {new_link}")


# 用一个可变 holder 让 clone_one 拿到总数,避免传一堆参数
item_total_holder: list[int] = [0]


async def main() -> None:
    sources = load_sources()
    item_total_holder[0] = len(sources)
    state = State.load()

    if not state.results:
        for i, url in enumerate(sources):
            idx = START_INDEX + i
            state.results.append(
                PackResult(
                    index=idx,
                    source_url=url,
                    new_short_name=f"{SHORT_PREFIX}_{idx:03d}",
                    new_title=NEW_TITLE,
                )
            )
        state.save()

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start(phone=PHONE)
    bot = await client.get_entity(BOT_USERNAME)
    print(f"已登录,bot = @{getattr(bot, 'username', BOT_USERNAME)}")

    try:
        for item in state.results:
            if item.status == "done":
                print(f"跳过已完成 #{item.index:03d} -> {item.new_url}")
                continue
            try:
                await clone_one(client, bot, item)
            except FloodWaitError as e:
                print(f"FloodWait {e.seconds}s, 等待...")
                await asyncio.sleep(e.seconds + 1)
                item.status = "pending"
                item.error = f"FloodWait {e.seconds}s, will retry"
            except Exception as e:
                item.status = "failed"
                item.error = repr(e)
                print(f"!! 异常: {e!r}")
            finally:
                state.save()
            await asyncio.sleep(PACK_DELAY)
    finally:
        await client.disconnect()
        state.save()
        done = sum(1 for r in state.results if r.status == "done")
        failed = sum(1 for r in state.results if r.status == "failed")
        print(f"\n完成 {done}/{len(state.results)},失败 {failed}。详情见 state.json")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n中断,进度已保存到 state.json,直接重跑即可继续。")
        sys.exit(130)
