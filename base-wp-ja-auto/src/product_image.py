"""BASE商品画像の生成。テンプレート画像があれば文字を差し替える。失敗しても登録全体は止めない。"""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import settings

logger = logging.getLogger("base_wp_ja_auto")

FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/YuGothM.ttc"),
    Path("C:/Windows/Fonts/meiryo.ttc"),
    Path("C:/Windows/Fonts/msgothic.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
]


def generate_product_image(plugin_name: str, dest: Path) -> Path | None:
    try:
        template = settings.templates_dir / "product_image.png"
        if template.exists():
            image = Image.open(template).convert("RGB")
        else:
            image = Image.new("RGB", (1200, 1200), (35, 40, 58))
            draw = ImageDraw.Draw(image)
            draw.rectangle((60, 60, 1140, 1140), outline=(255, 255, 255), width=6)
            draw.rectangle((60, 860, 1140, 1140), fill=(47, 111, 175))

        draw = ImageDraw.Draw(image)
        title_font = _font(64)
        sub_font = _font(48)
        small_font = _font(36)
        w, h = image.size
        _centered(draw, plugin_name[:40], y=int(h * 0.28), font=title_font, fill=(255, 255, 255), width=w)
        ja_label = "日本語化"
        try:
            _centered(draw, ja_label, y=int(h * 0.48), font=sub_font, fill=(255, 230, 150), width=w)
        except Exception:
            _centered(draw, "Japanese Localization", y=int(h * 0.48), font=sub_font, fill=(255, 230, 150), width=w)
        _centered(draw, "WordPress Plugin", y=int(h * 0.62), font=small_font, fill=(220, 230, 245), width=w)
        dest.parent.mkdir(parents=True, exist_ok=True)
        image.save(dest, format="PNG")
        logger.info("商品画像を生成: %s", dest)
        return dest
    except Exception as exc:  # noqa: BLE001
        logger.info("商品画像の自動生成に失敗したため手動確認待ちにします: %s", exc)
        return None


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _centered(draw: ImageDraw.ImageDraw, text: str, *, y: int, font, fill, width: int) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = max(40, (width - tw) // 2)
    draw.text((x, y), text, font=font, fill=fill)
