"""Cross-platform font helpers for CJK-safe text rendering."""

from __future__ import annotations

import os

from PIL import ImageFont


_CJK_LANGS = {"zh", "zh-cn", "zh-tw", "ja", "ko"}


def is_cjk_language(lang: str | None) -> bool:
    """Return True if language code should prefer CJK-capable fonts."""
    if not lang:
        return False
    norm = lang.strip().lower()
    return norm in _CJK_LANGS or norm.startswith("zh-")


def get_font(
    size: int,
    *,
    prefer_cjk: bool = False,
    bold: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a usable font, preferring CJK-capable fonts when requested."""
    latin_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    cjk_candidates = [
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/CJKSymbolsFallback.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/arialuni.ttf",
    ]

    candidates = (
        cjk_candidates + latin_candidates
        if prefer_cjk
        else latin_candidates + cjk_candidates
    )

    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                continue

    return ImageFont.load_default()
