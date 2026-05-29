"""tg_monitor —— Telegram 屏幕监控 + 关键词自动点击工具。

用「截屏 -> OCR 识别 -> 命中关键词 -> 自动移动鼠标点击」的方式，
盯着 Telegram 窗口（网页版 / 桌面版均可），一旦出现「领取」等关键词，
自动帮你点一下，避免人不在电脑前错过重要领取。

模块划分（便于离线测试，核心逻辑不依赖 GUI / OCR / 鼠标库）：
- config.py   配置（关键词、区域、间隔、冷却、是否真点击等），可存读 JSON。
- matcher.py  纯逻辑：在 OCR 结果里找关键词、命中去重 / 点击冷却。
- ocr.py      OCR 引擎封装（easyocr 优先，缺失时回退 pytesseract）。
- clicker.py  鼠标点击封装（pyautogui），支持「只提示不点击」演练模式。
- monitor.py  监控主循环，把上面拼起来，对外只暴露回调，UI 无关。
- gui.py      Tkinter 监控窗口：状态 / 日志 / 选区 / 启停。
"""

__version__ = "0.1.0"

from .config import MonitorConfig  # noqa: F401
from .matcher import KeywordMatcher, ClickGuard, Hit  # noqa: F401
