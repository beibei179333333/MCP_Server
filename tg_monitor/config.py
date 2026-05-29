"""监控配置：可保存 / 读取为 JSON，供 GUI 和命令行共用。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple


# 监控区域：(left, top, width, height)；None 表示全屏。
Region = Optional[Tuple[int, int, int, int]]


@dataclass
class MonitorConfig:
    # 要监控的关键词，命中任意一个即触发。默认就是你要的「领取」。
    keywords: List[str] = field(default_factory=lambda: ["领取"])

    # 监控区域 (left, top, width, height)；None = 全屏。
    # 强烈建议只框住 Telegram 聊天窗口，识别更快更准、也更安全。
    region: Region = None

    # 每隔多少秒截屏识别一次。太小会很吃 CPU，0.8~2 秒较合适。
    interval: float = 1.2

    # 点击冷却：触发一次点击后，至少隔这么多秒才允许再次点击，
    # 防止同一条「领取」按钮被疯狂连点。
    cooldown: float = 8.0

    # 同一位置去重半径（像素）：在冷却时间内，距上次点击点小于该值的命中会被跳过。
    dedupe_radius: int = 45

    # True = 真的移动鼠标并点击；False = 只在日志里提示、不点（演练 / 先观察用）。
    auto_click: bool = True

    # 命中时是否响铃提醒（终端响铃 / 系统提示音）。
    sound_alert: bool = True

    # OCR 引擎："auto" / "easyocr" / "tesseract"。
    ocr_engine: str = "auto"

    # OCR 识别语言。easyocr 用列表，tesseract 用 "chi_sim+eng"。
    ocr_languages: List[str] = field(default_factory=lambda: ["ch_sim", "en"])

    # 识别置信度下限（低于此值的文字忽略），0~1。
    min_confidence: float = 0.4

    # 点击前是否把鼠标移回原位（点完归位，少打扰你正在做的事）。
    restore_mouse: bool = True

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "MonitorConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "MonitorConfig":
        known = {k: v for k, v in (data or {}).items() if k in cls.__annotations__}
        if isinstance(known.get("region"), list):
            known["region"] = tuple(known["region"])  # JSON 里是 list，转回 tuple
        return cls(**known)
