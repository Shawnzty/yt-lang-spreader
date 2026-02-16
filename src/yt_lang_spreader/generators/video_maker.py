"""Extract key frames and assemble the final video with narration."""

from __future__ import annotations

import os
import subprocess
import tempfile

from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    concatenate_videoclips,
)
from PIL import Image, ImageDraw, ImageFont

from ..core.models import Segment
from ..utils.formatting import wrap_text

# Pillow>=10 removed Image.ANTIALIAS, but moviepy 1.x still references it.
if not hasattr(Image, "ANTIALIAS") and hasattr(Image, "Resampling"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS


def extract_key_frames(
    video_path: str,
    segments: list[Segment],
    output_dir: str,
    frames_per_segment: int = 3,
) -> list[Segment]:
    """Extract key frames from the video for each segment.

    Updates each segment's frame_paths in-place and returns the segments.
    """
    os.makedirs(output_dir, exist_ok=True)

    for segment in segments:
        duration = segment.end - segment.start
        if duration <= 0:
            continue

        interval = duration / (frames_per_segment + 1)
        for i in range(frames_per_segment):
            timestamp = segment.start + interval * (i + 1)
            frame_path = os.path.join(
                output_dir, f"frame_{segment.index:03d}_{i:02d}.jpg"
            )
            cmd = [
                "ffmpeg",
                "-ss", str(timestamp),
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "2",
                "-y",
                frame_path,
            ]
            subprocess.run(cmd, capture_output=True, text=True, check=False)
            if os.path.exists(frame_path):
                segment.frame_paths.append(frame_path)

    return segments


def create_video(
    segments: list[Segment],
    output_path: str,
    video_size: tuple[int, int] = (1280, 720),
    show_subtitles: bool = True,
) -> str:
    """Assemble the final video from segment data (frames, charts, audio).

    For each segment, displays key frames and any generated charts as a
    slideshow, with narration audio and optional subtitle overlay.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    clips = []
    w, h = video_size

    for segment in segments:
        if not segment.audio_path:
            continue

        text = segment.translated_summary or segment.summary
        audio_clip = AudioFileClip(segment.audio_path)
        seg_duration = audio_clip.duration

        # Combine key frames and chart images for this segment
        all_images = list(segment.frame_paths) + list(segment.chart_paths)

        if not all_images:
            clip = _create_text_only_clip(text, seg_duration, video_size)
            clip = clip.set_audio(audio_clip)
            clips.append(clip)
            continue

        # Create slideshow from images
        frame_duration = seg_duration / len(all_images)
        frame_clips = []
        for img_path in all_images:
            img_clip = (
                ImageClip(img_path)
                .set_duration(frame_duration)
                .resize(video_size)
            )
            frame_clips.append(img_clip)

        slideshow = concatenate_videoclips(frame_clips, method="compose")

        if show_subtitles and text:
            subtitle_clip = _create_subtitle_clip(text, seg_duration, video_size)
            final_clip = CompositeVideoClip(
                [slideshow, subtitle_clip.set_position(("center", h - 100))]
            )
        else:
            final_clip = slideshow

        final_clip = final_clip.set_audio(audio_clip)
        clips.append(final_clip)

    if not clips:
        raise RuntimeError("No video clips were generated. Check your input.")

    final_video = concatenate_videoclips(clips, method="compose")
    final_video.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=24,
        logger="bar",
    )
    final_video.close()
    for clip in clips:
        clip.close()

    return output_path


# ---------------------------------------------------------------------------
# Image clip helpers
# ---------------------------------------------------------------------------

def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load a TrueType font, fall back to default."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except (OSError, IOError):
                continue
    return ImageFont.load_default()


def _create_text_only_clip(
    text: str, duration: float, size: tuple[int, int]
) -> ImageClip:
    """Create a clip with text centred on a dark background."""
    w, h = size
    img = Image.new("RGB", (w, h), color=(20, 20, 30))
    draw = ImageDraw.Draw(img)
    font = _get_font(28)
    wrapped = wrap_text(text, max_chars=60)

    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (w - text_w) // 2
    y = (h - text_h) // 2
    draw.multiline_text((x, y), wrapped, fill="white", font=font, align="center")

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    img.save(tmp.name)
    tmp.close()
    return ImageClip(tmp.name).set_duration(duration)


def _create_subtitle_clip(
    text: str, duration: float, size: tuple[int, int]
) -> ImageClip:
    """Create a semi-transparent subtitle overlay clip."""
    w, _ = size
    sub_h = 80
    img = Image.new("RGBA", (w, sub_h), color=(0, 0, 0, 160))
    draw = ImageDraw.Draw(img)
    font = _get_font(20)

    display_text = text[:200] + "..." if len(text) > 200 else text
    wrapped = wrap_text(display_text, max_chars=80)

    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (w - text_w) // 2
    y = (sub_h - text_h) // 2
    draw.multiline_text((x, y), wrapped, fill="white", font=font, align="center")

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    img.save(tmp.name)
    tmp.close()
    return ImageClip(tmp.name).set_duration(duration)
