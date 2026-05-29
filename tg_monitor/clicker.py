"""鼠标点击封装（pyautogui），支持演练模式（只提示不点）。"""

from __future__ import annotations

from typing import Optional, Tuple


class Clicker:
    def __init__(self, auto_click: bool = True, restore_mouse: bool = True):
        self.auto_click = auto_click
        self.restore_mouse = restore_mouse
        self._pyautogui = None

    def _lazy(self):
        if self._pyautogui is None:
            try:
                import pyautogui  # type: ignore
            except ImportError as e:
                raise RuntimeError(
                    "未安装 pyautogui。请运行：pip install pyautogui"
                ) from e
            # 故障保护：把鼠标猛甩到屏幕左上角即可强制中止，防止失控。
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.02
            self._pyautogui = pyautogui
        return self._pyautogui

    def click(self, x: int, y: int) -> bool:
        """在 (x, y) 处点击。auto_click=False 时只返回 False（不真点）。

        返回是否真的执行了点击。
        """
        if not self.auto_click:
            return False
        pg = self._lazy()
        origin: Optional[Tuple[int, int]] = pg.position() if self.restore_mouse else None
        pg.moveTo(x, y, duration=0.15)
        pg.click()
        if origin is not None:
            pg.moveTo(origin[0], origin[1], duration=0.1)
        return True
