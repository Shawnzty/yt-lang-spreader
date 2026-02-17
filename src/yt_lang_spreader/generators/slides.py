"""Generate clean info slides for macro/general segments.

For segments about Fed meetings, macro economics, or general market news,
we generate presentation-style slides with bullet points instead of
using screenshots from the original video.
"""

from __future__ import annotations

import json
import os
import re
import textwrap

from PIL import Image, ImageDraw, ImageFont

from ..core.models import Segment


# ---------------------------------------------------------------------------
# Bullet-point extraction via GPT
# ---------------------------------------------------------------------------

def extract_bullet_points(
    segment: Segment,
    api_key: str,
    model: str = "gpt-4o-mini",
) -> list[dict]:
    """Use GPT to extract structured bullet points from a macro segment.

    Returns a list of slide dicts:
    [
        {"title": "Fed Rate Decision", "bullets": ["Rates held at 5.25%", ...]},
        {"title": "CPI Data", "bullets": ["CPI came in at 3.2%", ...]},
    ]
    """
    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    prompt = (
        "Extract the key information from this finance video transcript segment "
        "and organize it into slides. Each slide should have a short title and "
        "3-6 concise bullet points. Keep bullets under 60 characters each.\n\n"
        f"Topic: {segment.topic_label or 'Market Overview'}\n\n"
        f"Transcript:\n{segment.text}\n\n"
        "Return ONLY a JSON array of slide objects:\n"
        '[{"title": "...", "bullets": ["...", "..."]}, ...]'
    )

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    slides = json.loads(raw)
    if isinstance(slides, list):
        return slides
    return [slides]


# ---------------------------------------------------------------------------
# Slide image rendering
# ---------------------------------------------------------------------------

_SLIDE_BG = (18, 18, 28)  # dark navy
_TITLE_COLOR = (255, 255, 255)
_BULLET_COLOR = (220, 220, 230)
_ACCENT_COLOR = (66, 165, 245)  # blue accent


def generate_slides(
    segment: Segment,
    output_dir: str,
    api_key: str = "",
    model: str = "gpt-4o-mini",
    size: tuple[int, int] = (1280, 720),
) -> list[str]:
    """Generate slide images for a macro segment.

    If an API key is available, uses GPT to extract structured bullets.
    Otherwise, creates a simple text slide from the summary.

    Returns list of saved image paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    paths: list[str] = []

    if api_key:
        try:
            slides_data = extract_bullet_points(segment, api_key, model)
        except Exception as e:
            print(f"      Slide extraction failed for segment {segment.index}: {e}")
            slides_data = _fallback_slides(segment)
    else:
        slides_data = _fallback_slides(segment)

    for slide_idx, slide in enumerate(slides_data):
        img_path = os.path.join(
            output_dir, f"slide_{segment.index:03d}_{slide_idx:02d}.png"
        )
        _render_slide(
            title=slide.get("title", segment.topic_label or "Market Overview"),
            bullets=slide.get("bullets", []),
            output_path=img_path,
            size=size,
        )
        paths.append(img_path)

    return paths


def _fallback_slides(segment: Segment) -> list[dict]:
    """Create simple slide data from the segment summary (no GPT)."""
    text = segment.summary or segment.text
    sentences = re.split(r"[.!?。！？]+", text)
    bullets = [s.strip() for s in sentences if s.strip()][:6]
    return [{
        "title": segment.topic_label or "Market Overview",
        "bullets": bullets,
    }]


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load a suitable font."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for fp in candidates:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except (OSError, IOError):
                continue
    return ImageFont.load_default()


def _render_slide(
    title: str,
    bullets: list[str],
    output_path: str,
    size: tuple[int, int] = (1280, 720),
) -> None:
    """Render a single slide image with a title and bullet points."""
    w, h = size
    img = Image.new("RGB", (w, h), color=_SLIDE_BG)
    draw = ImageDraw.Draw(img)

    margin_x = 80
    current_y = 60

    # --- Title ---
    title_font = _get_font(36)
    # Draw accent line above title
    draw.rectangle(
        [margin_x, current_y, margin_x + 60, current_y + 4],
        fill=_ACCENT_COLOR,
    )
    current_y += 16

    title_wrapped = textwrap.fill(title, width=40)
    draw.multiline_text(
        (margin_x, current_y), title_wrapped, fill=_TITLE_COLOR, font=title_font,
    )
    title_bbox = draw.multiline_textbbox(
        (margin_x, current_y), title_wrapped, font=title_font
    )
    current_y = title_bbox[3] + 30

    # --- Separator line ---
    draw.line(
        [(margin_x, current_y), (w - margin_x, current_y)],
        fill=_ACCENT_COLOR,
        width=1,
    )
    current_y += 25

    # --- Bullet points ---
    bullet_font = _get_font(24)
    bullet_spacing = 12

    for bullet_text in bullets:
        if current_y > h - 60:
            break

        wrapped = textwrap.fill(bullet_text.strip(), width=55)
        lines = wrapped.split("\n")

        # Draw bullet dot
        dot_y = current_y + 8
        draw.ellipse(
            [margin_x + 5, dot_y, margin_x + 13, dot_y + 8],
            fill=_ACCENT_COLOR,
        )

        text_x = margin_x + 28
        for line in lines:
            draw.text((text_x, current_y), line, fill=_BULLET_COLOR, font=bullet_font)
            line_bbox = draw.textbbox((text_x, current_y), line, font=bullet_font)
            current_y = line_bbox[3] + 4

        current_y += bullet_spacing

    img.save(output_path, "PNG")
