"""
用 Bot API 直接批量克隆 Telegram 表情包并统一重命名。

和 @fStikBot 无关:本脚本用你自己的 bot(@Biaoqing111bot)的 token,
直接调用 Bot API 把源表情包复制成新的、归你 bot 所有的包。

对 packs.txt 里每个源链接:
  1. 从链接解析出源 short_name(如 tie105_by_fStikBot)
  2. getStickerSet 读取源包的全部贴纸 / 自定义 emoji
  3. createNewStickerSet 建新包(前 50 个),addStickerToSet 补齐其余
       new name  = <SHORT_PREFIX>_<NNN>_by_<bot用户名>   (如 emojipd_001_by_Biaoqing111bot)
       new title = 会员表情🔥 @emojipd
       sticker_type / format 自动沿用源包
  4. 把新链接写入 state.json

特性:
  - 进度持久化在 state.json,断了重跑会跳过已完成的包
  - 默认复用源 file_id(快);若失败自动回退到“下载再上传”
  - 自动处理 429 限速(按 retry_after 等待重试)

新包链接形如:
  custom_emoji -> https://t.me/addemoji/emojipd_001_by_Biaoqing111bot
  regular      -> https://t.me/addstickers/emojipd_014_by_Biaoqing111bot
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ["TG_BOT_TOKEN"]
API = f"https://api.telegram.org/bot{TOKEN}"
FILE_API = f"https://api.telegram.org/file/bot{TOKEN}"

NEW_TITLE = os.environ.get("NEW_TITLE", "会员表情🔥 @emojipd")
SHORT_PREFIX = os.environ.get("SHORT_PREFIX", "emojipd")
START_INDEX = int(os.environ.get("START_INDEX", "1"))
OWNER_ID_ENV = os.environ.get("BOT_OWNER_ID", "").strip()
REUSE_FILE_ID = os.environ.get("REUSE_FILE_ID", "1") not in ("0", "false", "False", "")
PACK_DELAY = float(os.environ.get("PACK_DELAY", "3"))
TEST_LIMIT = int(os.environ.get("TEST_LIMIT", "0"))

ROOT = Path(__file__).parent
PACKS_FILE = ROOT / "packs.txt"
STATE_FILE = ROOT / "state_bot.json"

CREATE_BATCH = 50      # createNewStickerSet 最多 50 个初始贴纸
HTTP_TIMEOUT = 60


# ----------------------------- Bot API 封装 -----------------------------

class ApiError(Exception):
    def __init__(self, method: str, payload: dict):
        self.method = method
        self.payload = payload
        super().__init__(f"{method} 失败: {payload}")


def _handle(method: str, resp: requests.Response) -> Any:
    data = resp.json()
    if data.get("ok"):
        return data["result"]
    # 429 限速:等待后重试
    if data.get("error_code") == 429:
        retry = data.get("parameters", {}).get("retry_after", 3)
        print(f"  429 限速,等待 {retry}s 后重试 {method} ...")
        time.sleep(retry + 1)
        return None  # 触发上层重试
    raise ApiError(method, data)


def call(method: str, **params) -> Any:
    while True:
        resp = requests.post(f"{API}/{method}", data=params, timeout=HTTP_TIMEOUT)
        result = _handle(method, resp)
        if result is not None:
            return result


def call_multipart(method: str, data: dict, files: dict) -> Any:
    while True:
        resp = requests.post(f"{API}/{method}", data=data, files=files, timeout=HTTP_TIMEOUT)
        result = _handle(method, resp)
        if result is not None:
            return result


def download_file(file_id: str) -> tuple[bytes, str, str]:
    """返回 (文件字节, 文件名, content-type)。"""
    info = call("getFile", file_id=file_id)
    file_path = info["file_path"]
    r = requests.get(f"{FILE_API}/{file_path}", timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    fname = os.path.basename(file_path)
    ctype = mimetypes.guess_type(fname)[0] or "application/octet-stream"
    return r.content, fname, ctype


# ----------------------------- 业务逻辑 -----------------------------

SOURCE_RE = re.compile(r"/add(?:emoji|stickers)/([\w]+)")


def source_name(url: str) -> str:
    m = SOURCE_RE.search(url)
    if not m:
        raise ValueError(f"无法从链接解析 short_name: {url}")
    return m.group(1)


def sticker_format(st: dict) -> str:
    if st.get("is_animated"):
        return "animated"
    if st.get("is_video"):
        return "video"
    return "static"


def emoji_list_of(st: dict) -> list[str]:
    e = st.get("emoji")
    return [e] if e else ["🙂"]


def public_link(name: str, sticker_type: str) -> str:
    kind = "addemoji" if sticker_type == "custom_emoji" else "addstickers"
    return f"https://t.me/{kind}/{name}"


@dataclass
class PackResult:
    index: int
    source_url: str
    source_name: str
    new_name: str = ""
    new_title: str = NEW_TITLE
    new_url: Optional[str] = None
    sticker_count: int = 0
    status: str = "pending"   # pending | done | failed
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
            json.dumps({"results": [asdict(r) for r in self.results]},
                       ensure_ascii=False, indent=2)
        )


def resolve_owner_id() -> int:
    if OWNER_ID_ENV:
        return int(OWNER_ID_ENV)
    print("BOT_OWNER_ID 未设置,尝试从 getUpdates 自动获取...")
    updates = call("getUpdates", limit=20)
    for u in reversed(updates):
        msg = u.get("message") or u.get("edited_message")
        if msg and msg.get("from"):
            uid = msg["from"]["id"]
            name = msg["from"].get("username") or msg["from"].get("first_name")
            print(f"  使用最近给 bot 发消息的用户: {uid} ({name})")
            return uid
    raise SystemExit(
        "无法确定包归属用户。请先用你的 Telegram 账号给 @Biaoqing111bot 发一条消息,"
        "再重跑;或在 .env 里设置 BOT_OWNER_ID=<你的数字user_id>。"
    )


def build_stickers(src_stickers: list[dict], use_file_id: bool):
    """返回 (input_stickers_json_list, files_dict)。"""
    input_stickers = []
    files: dict[str, tuple[str, bytes, str]] = {}
    for i, st in enumerate(src_stickers):
        item = {"format": sticker_format(st), "emoji_list": emoji_list_of(st)}
        if use_file_id:
            item["sticker"] = st["file_id"]
        else:
            content, fname, ctype = download_file(st["file_id"])
            attach = f"sticker_{i}"
            files[attach] = (fname, content, ctype)
            item["sticker"] = f"attach://{attach}"
        input_stickers.append(item)
    return input_stickers, files


def create_set(owner: int, name: str, title: str, sticker_type: str,
               input_stickers: list[dict], files: dict) -> None:
    data = {
        "user_id": owner,
        "name": name,
        "title": title,
        "sticker_type": sticker_type,
        "stickers": json.dumps(input_stickers, ensure_ascii=False),
    }
    if files:
        call_multipart("createNewStickerSet", data, files)
    else:
        call("createNewStickerSet", **data)


def add_one(owner: int, name: str, st_input: dict, files: dict) -> None:
    data = {
        "user_id": owner,
        "name": name,
        "sticker": json.dumps(st_input, ensure_ascii=False),
    }
    if files:
        call_multipart("addStickerToSet", data, files)
    else:
        call("addStickerToSet", **data)


def clone_pack(owner: int, item: PackResult) -> None:
    src = call("getStickerSet", name=item.source_name)
    src_stickers = src["stickers"]
    sticker_type = src.get("sticker_type", "regular")
    item.sticker_count = len(src_stickers)
    print(f"  源包 {item.source_name}: {len(src_stickers)} 个 ({sticker_type})")

    if not src_stickers:
        raise RuntimeError("源包没有贴纸")

    use_file_id = REUSE_FILE_ID

    def do_clone(reuse: bool) -> None:
        first = src_stickers[:CREATE_BATCH]
        rest = src_stickers[CREATE_BATCH:]
        ins, files = build_stickers(first, reuse)
        create_set(owner, item.new_name, item.new_title, sticker_type, ins, files)
        for st in rest:
            ins1, files1 = build_stickers([st], reuse)
            add_one(owner, item.new_name, ins1[0], files1)
            time.sleep(0.5)

    try:
        do_clone(use_file_id)
    except ApiError as e:
        if use_file_id:
            print(f"  复用 file_id 失败({e.payload.get('description')}),"
                  f"回退到下载再上传 ...")
            # 失败时新包可能已部分建立,先尝试删掉再重建
            try:
                call("deleteStickerSet", name=item.new_name)
            except ApiError:
                pass
            do_clone(False)
        else:
            raise

    item.new_url = public_link(item.new_name, sticker_type)
    item.status = "done"
    print(f"  OK -> {item.new_url}")


def load_sources() -> list[str]:
    urls = []
    for line in PACKS_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def main() -> None:
    me = call("getMe")
    bot_username = me["username"]
    print(f"已连接 bot: @{bot_username}")

    owner = resolve_owner_id()
    sources = load_sources()
    if TEST_LIMIT > 0:
        sources = sources[:TEST_LIMIT]
        print(f"测试模式:只处理前 {TEST_LIMIT} 个包")

    state = State.load()
    if not state.results:
        for i, url in enumerate(sources):
            idx = START_INDEX + i
            state.results.append(PackResult(
                index=idx,
                source_url=url,
                source_name=source_name(url),
                new_name=f"{SHORT_PREFIX}_{idx:03d}_by_{bot_username}",
            ))
        state.save()

    total = len(state.results)
    for item in state.results:
        if item.status == "done":
            print(f"跳过已完成 #{item.index:03d} -> {item.new_url}")
            continue
        print(f"\n=== [{item.index:03d}/{START_INDEX + total - 1}] "
              f"{item.source_url} -> {item.new_name} ===")
        try:
            clone_pack(owner, item)
        except Exception as e:  # noqa: BLE001
            item.status = "failed"
            item.error = str(e)
            print(f"  !! 失败: {e}")
        finally:
            state.save()
        time.sleep(PACK_DELAY)

    done = sum(1 for r in state.results if r.status == "done")
    failed = sum(1 for r in state.results if r.status == "failed")
    print(f"\n完成 {done}/{total},失败 {failed}。详情见 state_bot.json")
    if failed:
        print("失败的包:")
        for r in state.results:
            if r.status == "failed":
                print(f"  #{r.index:03d} {r.source_name}: {r.error}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n中断,进度已存到 state_bot.json,重跑即可继续。")
        sys.exit(130)
