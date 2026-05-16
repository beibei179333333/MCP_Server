"""图片水印插件（基于 Pillow）。"""
from __future__ import annotations

import io
import logging

from .base import BasePlugin, MessageContext, PluginResult
from .registry import register

log = logging.getLogger(__name__)


@register("watermark")
class WatermarkPlugin(BasePlugin):
    """
    在图片右下角加文字水印。
    cfg = {
        "text": "@MyChannel",
        "position": "br",      # tl/tr/bl/br/center
        "opacity": 160,         # 0-255
        "font_size": 28,
    }
    """

    async def process(self, ctx: MessageContext) -> PluginResult:
        if ctx.media_type != "photo" or not ctx.media_bytes:
            return PluginResult.CONTINUE
        text = self.cfg.get("text") or ""
        if not text:
            return PluginResult.CONTINUE

        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            return PluginResult.CONTINUE

        try:
            img = Image.open(io.BytesIO(ctx.media_bytes)).convert("RGBA")
        except Exception as e:  # noqa: BLE001
            log.warning("watermark: 无法打开图片: %s", e)
            return PluginResult.CONTINUE

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        try:
            font = ImageFont.truetype("DejaVuSans.ttf", int(self.cfg.get("font_size", 28)))
        except Exception:  # noqa: BLE001
            font = ImageFont.load_default()

        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            tw, th = font.getsize(text)  # type: ignore[attr-defined]

        pad = 18
        pos = self.cfg.get("position", "br")
        if pos == "tl":
            xy = (pad, pad)
        elif pos == "tr":
            xy = (img.width - tw - pad, pad)
        elif pos == "bl":
            xy = (pad, img.height - th - pad)
        elif pos == "center":
            xy = ((img.width - tw) // 2, (img.height - th) // 2)
        else:  # br
            xy = (img.width - tw - pad, img.height - th - pad)

        opacity = int(self.cfg.get("opacity", 160))
        draw.text((xy[0] + 2, xy[1] + 2), text, font=font, fill=(0, 0, 0, opacity))
        draw.text(xy, text, font=font, fill=(255, 255, 255, opacity))

        out = Image.alpha_composite(img, overlay).convert("RGB")
        buf = io.BytesIO()
        out.save(buf, format="JPEG", quality=92)
        ctx.media_bytes = buf.getvalue()
        ctx.media_mime = "image/jpeg"
        return PluginResult.CONTINUE
