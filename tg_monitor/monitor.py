"""监控主循环：截屏 -> OCR -> 匹配关键词 -> （去重/冷却后）自动点击。

设计成 UI 无关：所有进展通过 `on_event` 回调抛出，GUI / 命令行各自渲染。
循环跑在后台线程里，调用 stop() 可优雅结束。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .config import MonitorConfig
from .clicker import Clicker
from .matcher import KeywordMatcher, ClickGuard, pick_best, Hit


@dataclass
class MonitorEvent:
    kind: str           # "info" | "scan" | "hit" | "click" | "skip" | "error" | "state"
    message: str = ""
    hit: Optional[Hit] = None
    clicked: bool = False
    timestamp: float = field(default_factory=time.time)


EventCallback = Callable[[MonitorEvent], None]


@dataclass
class MonitorStats:
    scans: int = 0
    hits: int = 0
    clicks: int = 0


class Monitor:
    def __init__(
        self,
        config: MonitorConfig,
        on_event: Optional[EventCallback] = None,
        ocr_engine=None,
        clicker: Optional[Clicker] = None,
    ):
        self.config = config
        self.on_event = on_event or (lambda e: None)
        self._engine = ocr_engine  # 允许注入（测试 / 复用已加载模型）
        self.clicker = clicker or Clicker(
            auto_click=config.auto_click, restore_mouse=config.restore_mouse
        )
        self.matcher = KeywordMatcher(config.keywords, config.min_confidence)
        self.guard = ClickGuard(config.cooldown, config.dedupe_radius)
        self.stats = MonitorStats()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---- 生命周期 ----
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="tg-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: Optional[float] = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ---- 内部 ----
    def _emit(self, kind: str, message: str = "", **kw) -> None:
        try:
            self.on_event(MonitorEvent(kind=kind, message=message, **kw))
        except Exception:
            pass  # UI 回调出错不能拖垮监控循环

    def _ensure_engine(self):
        if self._engine is None:
            from .ocr import build_engine
            self._emit("info", "正在加载 OCR 识别引擎（首次可能要下载模型，请稍候）…")
            self._engine = build_engine(self.config.ocr_engine, self.config.ocr_languages)
            self._emit("info", "OCR 引擎已就绪。")
        return self._engine

    def _run(self) -> None:
        self._emit("state", "started")
        try:
            from .ocr import grab_screen
            engine = self._ensure_engine()
        except Exception as e:
            self._emit("error", f"启动失败：{e}")
            self._emit("state", "stopped")
            return

        region = self.config.region
        offset = (region[0], region[1]) if region else (0, 0)
        mode = "自动点击" if self.config.auto_click else "仅提示(不点击)"
        self._emit(
            "info",
            f"开始监控。关键词={self.config.keywords}，模式={mode}，"
            f"间隔={self.config.interval}s。把鼠标甩到屏幕左上角可紧急中止点击。",
        )

        while not self._stop.is_set():
            loop_start = time.time()
            try:
                img = grab_screen(region)
                boxes = engine.read(img, offset=offset)
                self.stats.scans += 1
                hits = self.matcher.match(boxes)
                if hits:
                    self._handle_hits(hits)
                else:
                    self._emit("scan", f"第 {self.stats.scans} 次扫描：未发现关键词。")
            except Exception as e:
                self._emit("error", f"扫描出错：{e}")

            # 控制节奏：扣掉本轮耗时，剩余时间分段 sleep 以便及时响应停止
            elapsed = time.time() - loop_start
            self._sleep(max(0.0, self.config.interval - elapsed))

        self._emit("info", "已停止监控。")
        self._emit("state", "stopped")

    def _handle_hits(self, hits) -> None:
        self.stats.hits += len(hits)
        best = pick_best(hits)
        if best is None:
            return
        self._emit(
            "hit",
            f"发现关键词「{best.keyword}」: \"{best.text}\" @({best.x},{best.y}) "
            f"置信度{best.confidence:.2f}",
            hit=best,
        )
        if self.config.sound_alert:
            self._beep()

        now = time.time()
        if not self.guard.should_click(best.x, best.y, now):
            self._emit("skip", "命中处于冷却/去重期内，本次不点击。", hit=best)
            return

        if not self.config.auto_click:
            self._emit("skip", "演练模式：仅提示，不实际点击。", hit=best)
            return

        try:
            clicked = self.clicker.click(best.x, best.y)
            if clicked:
                self.stats.clicks += 1
                self._emit("click", f"已自动点击 ({best.x},{best.y})。", hit=best, clicked=True)
        except Exception as e:
            self._emit("error", f"点击失败：{e}")

    def _sleep(self, seconds: float) -> None:
        # 分段等待，最长 0.2s 检查一次停止标志
        end = time.time() + seconds
        while not self._stop.is_set() and time.time() < end:
            time.sleep(min(0.2, end - time.time()))

    def _beep(self) -> None:
        try:
            print("\a", end="", flush=True)  # 终端响铃
        except Exception:
            pass
