"""Extract key frames and assemble the final video with narration."""

import os
import subprocess

from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    concatenate_videoclips,
)

from .segmenter import Segment, format_timestamp


def extract_key_frames(
    video_path: str,
    segments: list[Segment],
    output_dir: str,
    frames_per_segment: int = 3,
) -> list[list[str]]:
    """Extract key frames from the video for each segment.

    Uses ffmpeg scene detection to find the most interesting frames
    within each segment's time range.

    Args:
        video_path: Path to the source video file.
        segments: List of segments defining time ranges.
        output_dir: Directory to save extracted frames.
        frames_per_segment: Number of frames to extract per segment.

    Returns:
        List of lists of image paths, one list per segment.
    """
    os.makedirs(output_dir, exist_ok=True)
    all_frame_paths = []

    for segment in segments:
        seg_frames = []
        duration = segment.end - segment.start

        if duration <= 0:
            all_frame_paths.append([])
            continue

        # Extract frames at evenly spaced intervals within the segment
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
            subprocess.run(
                cmd, capture_output=True, text=True, check=False
            )

            if os.path.exists(frame_path):
                seg_frames.append(frame_path)

        all_frame_paths.append(seg_frames)

    return all_frame_paths


def create_video(
    segments: list[Segment],
    frame_paths: list[list[str]],
    audio_paths: list[str],
    output_path: str,
    target_lang: str,
    video_size: tuple[int, int] = (1280, 720),
    show_subtitles: bool = True,
) -> str:
    """Assemble the final video from frames, narration audio, and subtitles.

    For each segment:
    - Use the narration audio to determine clip duration
    - Display key frames as a slideshow
    - Overlay translated subtitle text at the bottom

    Args:
        segments: List of Segment objects with summaries.
        frame_paths: Key frame image paths per segment.
        audio_paths: Narration audio paths per segment.
        output_path: Output video file path.
        target_lang: Target language (used for subtitle styling).
        video_size: Output video resolution (width, height).
        show_subtitles: Whether to show subtitle overlay.

    Returns:
        Path to the created video file.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    clips = []
    w, h = video_size

    for idx, (segment, frames, audio_path) in enumerate(
        zip(segments, frame_paths, audio_paths)
    ):
        text = segment.translated_summary or segment.summary
        if not text or not audio_path:
            continue

        # Load audio to get duration
        audio_clip = AudioFileClip(audio_path)
        seg_duration = audio_clip.duration

        if not frames:
            # No frames: create a black background with text
            clip = _create_text_only_clip(text, seg_duration, video_size)
            clip = clip.set_audio(audio_clip)
            clips.append(clip)
            continue

        # Create slideshow from key frames
        frame_duration = seg_duration / len(frames)
        frame_clips = []

        for frame_path in frames:
            img_clip = (
                ImageClip(frame_path)
                .set_duration(frame_duration)
                .resize(video_size)
            )
            frame_clips.append(img_clip)

        slideshow = concatenate_videoclips(frame_clips, method="compose")

        # Add subtitle overlay if requested
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

    # Concatenate all segment clips
    final_video = concatenate_videoclips(clips, method="compose")
    final_video.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=24,
        logger="bar",
    )

    # Clean up
    final_video.close()
    for clip in clips:
        clip.close()

    return output_path


def _create_text_only_clip(
    text: str, duration: float, size: tuple[int, int]
) -> ImageClip:
    """Create a simple clip with text on a dark background."""
    from PIL import Image, ImageDraw, ImageFont
    import tempfile

    w, h = size
    img = Image.new("RGB", (w, h), color=(20, 20, 30))
    draw = ImageDraw.Draw(img)

    # Wrap text to fit
    wrapped = _wrap_text(text, max_chars=60)

    # Use default font
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except (OSError, IOError):
        font = ImageFont.load_default()

    # Calculate text position (centered)
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
    """Create a subtitle overlay clip."""
    from PIL import Image, ImageDraw, ImageFont
    import tempfile

    w, h = size
    sub_h = 80
    img = Image.new("RGBA", (w, sub_h), color=(0, 0, 0, 160))
    draw = ImageDraw.Draw(img)

    # Truncate long subtitles for display
    display_text = text[:200] + "..." if len(text) > 200 else text
    wrapped = _wrap_text(display_text, max_chars=80)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    except (OSError, IOError):
        font = ImageFont.load_default()

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


def _wrap_text(text: str, max_chars: int = 60) -> str:
    """Simple word-wrapping for text."""
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        if len(current_line) + len(word) + 1 <= max_chars:
            current_line = f"{current_line} {word}" if current_line else word
        else:
            if current_line:
                lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return "\n".join(lines)
