"""命令行入口。

  python -m tg_monitor                # 打开图形监控窗口（推荐）
  python -m tg_monitor --no-gui       # 无界面，纯终端监控
  python -m tg_monitor -k 领取 红包    # 指定关键词
  python -m tg_monitor --dry-run      # 只提示不点击（先观察）
  python -m tg_monitor --region 100 200 800 600   # 指定监控区域 left top w h
  python -m tg_monitor --config my.json           # 从配置文件读
"""

from __future__ import annotations

import argparse
import sys
import time

from .config import MonitorConfig


def build_config(args) -> MonitorConfig:
    if args.config:
        cfg = MonitorConfig.load(args.config)
    else:
        cfg = MonitorConfig()
    if args.keywords:
        cfg.keywords = args.keywords
    if args.interval is not None:
        cfg.interval = args.interval
    if args.cooldown is not None:
        cfg.cooldown = args.cooldown
    if args.region is not None:
        cfg.region = tuple(args.region)  # type: ignore
    if args.dry_run:
        cfg.auto_click = False
    if args.engine:
        cfg.ocr_engine = args.engine
    return cfg


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="tg_monitor",
        description="Telegram 屏幕监控：检测到「领取」等关键词时自动点击鼠标。",
    )
    p.add_argument("-k", "--keywords", nargs="+", help="关键词（可多个），默认：领取")
    p.add_argument("-i", "--interval", type=float, help="扫描间隔秒数，默认 1.2")
    p.add_argument("-c", "--cooldown", type=float, help="点击冷却秒数，默认 8")
    p.add_argument("--region", nargs=4, type=int, metavar=("LEFT", "TOP", "W", "H"),
                   help="监控区域；不填则全屏")
    p.add_argument("--dry-run", action="store_true", help="只提示不点击（先观察）")
    p.add_argument("--engine", choices=["auto", "easyocr", "tesseract"], help="OCR 引擎")
    p.add_argument("--no-gui", action="store_true", help="不开图形界面，纯终端运行")
    p.add_argument("--config", help="从 JSON 配置文件读取")
    p.add_argument("--save-config", help="把当前设置保存到 JSON 后退出")
    args = p.parse_args(argv)

    cfg = build_config(args)

    if args.save_config:
        cfg.save(args.save_config)
        print(f"已保存配置到 {args.save_config}")
        return 0

    if args.no_gui:
        return run_headless(cfg)

    try:
        from .gui import run_gui
        run_gui(cfg)
        return 0
    except Exception as e:
        print(f"无法打开图形界面（{e}）；改用终端模式。可加 --no-gui 直接用终端。")
        return run_headless(cfg)


def run_headless(cfg: MonitorConfig) -> int:
    from .monitor import Monitor, MonitorEvent

    def on_event(ev: MonitorEvent):
        if ev.kind == "scan":
            return  # 终端下不刷扫描噪音
        if ev.message:
            print(f"[{time.strftime('%H:%M:%S')}] {ev.message}")

    m = Monitor(cfg, on_event=on_event)
    print("开始终端监控，按 Ctrl+C 停止。")
    m.start()
    try:
        while m.running:
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\n收到停止信号…")
        m.stop()
        m.join(timeout=3)
    return 0


if __name__ == "__main__":
    sys.exit(main())
