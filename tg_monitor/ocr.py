"""屏幕截图 + OCR 识别封装。

依赖均为「按需导入」，缺哪个只在真正用到时报清晰的中文提示，
这样核心逻辑（matcher）可以在没装这些重库的机器上照样跑测试。

OCR 引擎：
- easyocr  ：纯 pip 安装，中文识别效果好（首次会自动下载模型）。推荐。
- tesseract：需另装 Tesseract 程序 + 中文语言包，体积小但中文需配置。

截图：优先用 mss（快），缺失时回退 pyautogui.screenshot。
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .config import Region
from .matcher import OcrBox


def grab_screen(region: Region = None):
    """截屏，返回 numpy RGB 数组。region=(left,top,w,h)，None=全屏。"""
    try:
        import numpy as np
        import mss  # type: ignore
    except ImportError:
        return _grab_with_pyautogui(region)

    with mss.mss() as sct:
        if region:
            l, t, w, h = region
            monitor = {"left": l, "top": t, "width": w, "height": h}
        else:
            monitor = sct.monitors[0]  # 整个虚拟屏幕
        raw = sct.grab(monitor)
        img = np.array(raw)  # BGRA
        return img[:, :, :3][:, :, ::-1]  # -> RGB


def _grab_with_pyautogui(region: Region):
    try:
        import numpy as np
        import pyautogui  # type: ignore
    except ImportError as e:  # pragma: no cover - 环境相关
        raise RuntimeError(
            "缺少截图依赖。请安装：pip install mss numpy  （或 pip install pyautogui）"
        ) from e
    shot = pyautogui.screenshot(region=region) if region else pyautogui.screenshot()
    return np.array(shot)[:, :, :3]


class OcrEngine:
    """OCR 引擎抽象，统一返回 List[OcrBox]（屏幕绝对坐标）。"""

    def read(self, image, offset: Tuple[int, int] = (0, 0)) -> List[OcrBox]:
        raise NotImplementedError


class EasyOcrEngine(OcrEngine):
    def __init__(self, languages: Sequence[str] = ("ch_sim", "en")):
        try:
            import easyocr  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "未安装 easyocr。请运行：pip install easyocr\n"
                "（首次使用会自动下载中文识别模型，需要联网一次）"
            ) from e
        # gpu=False 兼容没有显卡的机器；有显卡可自行改 True 提速。
        self._reader = easyocr.Reader(list(languages), gpu=False)

    def read(self, image, offset: Tuple[int, int] = (0, 0)) -> List[OcrBox]:
        ox, oy = offset
        boxes: List[OcrBox] = []
        for bbox, text, conf in self._reader.readtext(image):
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            left, top = int(min(xs)), int(min(ys))
            w, h = int(max(xs) - left), int(max(ys) - top)
            boxes.append(
                OcrBox(text=text, box=(left + ox, top + oy, w, h), confidence=float(conf))
            )
        return boxes


class TesseractEngine(OcrEngine):
    def __init__(self, lang: str = "chi_sim+eng"):
        try:
            import pytesseract  # type: ignore  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "未安装 pytesseract。请运行：pip install pytesseract，"
                "并安装 Tesseract 程序及中文语言包(chi_sim)。"
            ) from e
        self.lang = lang

    def read(self, image, offset: Tuple[int, int] = (0, 0)) -> List[OcrBox]:
        import pytesseract  # type: ignore
        from pytesseract import Output  # type: ignore

        ox, oy = offset
        data = pytesseract.image_to_data(image, lang=self.lang, output_type=Output.DICT)
        boxes: List[OcrBox] = []
        n = len(data.get("text", []))
        for i in range(n):
            text = (data["text"][i] or "").strip()
            if not text:
                continue
            conf = float(data["conf"][i]) / 100.0 if data["conf"][i] not in ("-1", -1) else 0.0
            left, top = int(data["left"][i]) + ox, int(data["top"][i]) + oy
            w, h = int(data["width"][i]), int(data["height"][i])
            boxes.append(OcrBox(text=text, box=(left, top, w, h), confidence=conf))
        return boxes


def build_engine(name: str, languages: Sequence[str]) -> OcrEngine:
    """按配置创建 OCR 引擎。name: auto / easyocr / tesseract。"""
    name = (name or "auto").lower()
    if name == "easyocr":
        return EasyOcrEngine(languages)
    if name == "tesseract":
        return TesseractEngine(_to_tess_lang(languages))
    # auto：先试 easyocr，失败再试 tesseract
    try:
        return EasyOcrEngine(languages)
    except RuntimeError:
        return TesseractEngine(_to_tess_lang(languages))


def _to_tess_lang(languages: Sequence[str]) -> str:
    mapping = {"ch_sim": "chi_sim", "ch_tra": "chi_tra", "en": "eng"}
    parts = [mapping.get(l, l) for l in languages]
    return "+".join(parts) if parts else "chi_sim+eng"
