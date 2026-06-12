"""Entry point: ``python -m worldcup_bot``.

Subcommands:
  run        start the bot (default)
  check      validate config + data source without starting the bot
  selftest   run the offline event-detection self test
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys

from .config import Config


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_run(cfg: Config) -> int:
    from .bot import WorldCupBot
    from .telegram import TelegramError

    if not cfg.telegram_token:
        print("❌ 未设置 TELEGRAM_BOT_TOKEN。请在环境变量或 .env 中配置 BotFather 给的 Token。",
              file=sys.stderr)
        print("   示例：复制 .env.example 为 .env 并填入 TELEGRAM_BOT_TOKEN=123456:ABC...",
              file=sys.stderr)
        return 2
    try:
        bot = WorldCupBot(cfg)
    except TelegramError as exc:
        print(f"❌ 初始化失败：{exc}", file=sys.stderr)
        return 2

    def _graceful(signum, _frame):
        logging.getLogger("worldcup_bot").info("收到信号 %s，正在退出…", signum)
        bot.stop.set()

    signal.signal(signal.SIGINT, _graceful)
    try:
        signal.signal(signal.SIGTERM, _graceful)
    except (ValueError, AttributeError):  # not always available
        pass

    try:
        bot.run()
    except TelegramError as exc:
        print(f"❌ Telegram 连接失败：{exc}", file=sys.stderr)
        print("   请检查网络是否能访问 api.telegram.org，以及 Token 是否正确。", file=sys.stderr)
        return 1
    return 0


def cmd_check(cfg: Config) -> int:
    from .providers import build_provider
    from .storage import Storage

    print(f"provider          : {cfg.provider}")
    print(f"competition       : {cfg.competition}")
    print(f"poll interval     : {cfg.poll_interval}s")
    print(f"reminder window   : {cfg.reminder_minutes} min")
    print(f"timezone          : {cfg.timezone}")
    print(f"telegram token set : {'yes' if cfg.telegram_token else 'NO'}")
    for w in cfg.warnings:
        print(f"⚠️  {w}")
    storage = Storage(cfg.db_path, cfg.default_lang)
    provider = build_provider(cfg, storage=storage)
    matches = provider.get_matches()
    print(f"\n抓取到 {len(matches)} 场比赛：")
    for m in matches[:10]:
        print(f"  [{m.status:9}] {m.home} {m.score_str()} {m.away}")
    storage.close()
    if not matches:
        print("⚠️  没有取到比赛数据。", file=sys.stderr)
        return 1
    return 0


def cmd_selftest(_cfg: Config) -> int:
    from .selftest import run_selftest
    ok = run_selftest()
    return 0 if ok else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="worldcup_bot",
                                     description="2026 世界杯实时通知 Telegram 机器人")
    parser.add_argument("command", nargs="?", default="run",
                        choices=["run", "check", "selftest"])
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--env", default=".env", help="path to .env file")
    args = parser.parse_args(argv)

    _setup_logging(args.log_level)
    cfg = Config.load(args.env)

    if args.command == "run":
        return cmd_run(cfg)
    if args.command == "check":
        return cmd_check(cfg)
    if args.command == "selftest":
        return cmd_selftest(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
