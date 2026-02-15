"""Download YouTube videos and extract subtitles/transcripts."""

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass


@dataclass
class VideoInfo:
    """Metadata and paths for a downloaded YouTube video."""

    video_id: str
    title: str
    duration: float  # seconds
    video_path: str
    subtitles: list[dict]  # [{"start": float, "end": float, "text": str}, ...]


def download_video(url: str, output_dir: str) -> str:
    """Download a YouTube video and return the path to the downloaded file."""
    os.makedirs(output_dir, exist_ok=True)
    output_template = os.path.join(output_dir, "%(id)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", output_template,
        "--no-playlist",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)

    # Find the downloaded file
    for line in result.stdout.splitlines():
        if "Destination:" in line or "has already been downloaded" in line:
            pass  # yt-dlp logs these but we find the file below

    # Get the video ID to locate the file
    info = _get_video_info(url)
    video_path = os.path.join(output_dir, f"{info['id']}.mp4")
    if not os.path.exists(video_path):
        # Fallback: find any mp4 in the output dir
        for f in os.listdir(output_dir):
            if f.endswith(".mp4"):
                video_path = os.path.join(output_dir, f)
                break

    return video_path


def _get_video_info(url: str) -> dict:
    """Get video metadata using yt-dlp."""
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-download",
        "--no-playlist",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def extract_subtitles(url: str, output_dir: str, lang: str = "en") -> list[dict]:
    """Extract subtitles from a YouTube video.

    Tries in order:
    1. Manual subtitles in the requested language
    2. Auto-generated subtitles
    3. Whisper-based transcription (if available via yt-dlp)

    Returns a list of segments: [{"start": float, "end": float, "text": str}]
    """
    os.makedirs(output_dir, exist_ok=True)
    sub_path = os.path.join(output_dir, "subs")

    # Try to get subtitles (manual first, then auto-generated)
    cmd = [
        "yt-dlp",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", f"{lang}",
        "--sub-format", "json3",
        "--skip-download",
        "--no-playlist",
        "-o", sub_path,
        url,
    ]
    subprocess.run(cmd, capture_output=True, text=True)

    # Look for the subtitle file
    sub_file = None
    for fname in os.listdir(output_dir):
        if fname.startswith("subs") and fname.endswith(".json3"):
            sub_file = os.path.join(output_dir, fname)
            break

    if sub_file and os.path.exists(sub_file):
        return _parse_json3_subs(sub_file)

    # Fallback: try srv3 format
    cmd[-4] = "srv3"  # change sub-format
    subprocess.run(cmd, capture_output=True, text=True)

    for fname in os.listdir(output_dir):
        if fname.startswith("subs") and (
            fname.endswith(".srv3") or fname.endswith(".json3")
        ):
            sub_file = os.path.join(output_dir, fname)
            break

    if sub_file and os.path.exists(sub_file):
        return _parse_srv3_subs(sub_file)

    # Final fallback: get VTT subs
    cmd_vtt = [
        "yt-dlp",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", f"{lang}",
        "--sub-format", "vtt",
        "--skip-download",
        "--no-playlist",
        "-o", sub_path,
        url,
    ]
    subprocess.run(cmd_vtt, capture_output=True, text=True)

    for fname in os.listdir(output_dir):
        if fname.startswith("subs") and fname.endswith(".vtt"):
            sub_file = os.path.join(output_dir, fname)
            break

    if sub_file and os.path.exists(sub_file):
        return _parse_vtt_subs(sub_file)

    raise RuntimeError(
        f"Could not extract subtitles for language '{lang}'. "
        "The video may not have captions available."
    )


def _parse_json3_subs(filepath: str) -> list[dict]:
    """Parse YouTube json3 subtitle format."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = []
    for event in data.get("events", []):
        if "segs" not in event:
            continue
        text = "".join(seg.get("utf8", "") for seg in event["segs"]).strip()
        if not text or text == "\n":
            continue
        start_ms = event.get("tStartMs", 0)
        dur_ms = event.get("dDurationMs", 0)
        segments.append({
            "start": start_ms / 1000.0,
            "end": (start_ms + dur_ms) / 1000.0,
            "text": text,
        })

    return _merge_short_segments(segments)


def _parse_srv3_subs(filepath: str) -> list[dict]:
    """Parse YouTube srv3 (XML-based) subtitle format."""
    import xml.etree.ElementTree as ET

    tree = ET.parse(filepath)
    root = tree.getroot()
    segments = []

    for p in root.iter("p"):
        start_ms = int(p.get("t", 0))
        dur_ms = int(p.get("d", 0))
        text = "".join(p.itertext()).strip()
        if not text:
            continue
        segments.append({
            "start": start_ms / 1000.0,
            "end": (start_ms + dur_ms) / 1000.0,
            "text": text,
        })

    return _merge_short_segments(segments)


def _parse_vtt_subs(filepath: str) -> list[dict]:
    """Parse WebVTT subtitle format."""
    import re

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    segments = []
    # Match timestamp lines: 00:00:01.000 --> 00:00:04.000
    pattern = r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})"
    blocks = re.split(pattern, content)

    i = 1  # skip the header
    while i + 2 < len(blocks):
        start_str = blocks[i]
        end_str = blocks[i + 1]
        text_block = blocks[i + 2]

        # Clean up text: remove tags, extra whitespace
        text = re.sub(r"<[^>]+>", "", text_block).strip()
        text = re.sub(r"\n+", " ", text).strip()

        if text:
            segments.append({
                "start": _vtt_time_to_seconds(start_str),
                "end": _vtt_time_to_seconds(end_str),
                "text": text,
            })
        i += 3

    return _merge_short_segments(segments)


def _vtt_time_to_seconds(time_str: str) -> float:
    """Convert VTT timestamp (HH:MM:SS.mmm) to seconds."""
    parts = time_str.split(":")
    h, m = int(parts[0]), int(parts[1])
    s = float(parts[2])
    return h * 3600 + m * 60 + s


def _merge_short_segments(
    segments: list[dict], min_duration: float = 1.0
) -> list[dict]:
    """Merge very short consecutive segments into longer ones."""
    if not segments:
        return segments

    merged = [segments[0].copy()]
    for seg in segments[1:]:
        prev = merged[-1]
        gap = seg["start"] - prev["end"]
        # Merge if the previous segment is very short or there's no gap
        if prev["end"] - prev["start"] < min_duration or gap < 0.1:
            prev["end"] = seg["end"]
            prev["text"] = prev["text"] + " " + seg["text"]
        else:
            merged.append(seg.copy())

    return merged


def get_video_info(url: str, output_dir: str) -> VideoInfo:
    """Download video, extract subtitles, and return a VideoInfo object."""
    info = _get_video_info(url)
    video_path = download_video(url, output_dir)
    subtitles = extract_subtitles(url, output_dir, lang="en")

    return VideoInfo(
        video_id=info["id"],
        title=info.get("title", "Untitled"),
        duration=info.get("duration", 0),
        video_path=video_path,
        subtitles=subtitles,
    )
