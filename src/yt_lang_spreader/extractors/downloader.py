"""Download YouTube videos and extract subtitles/transcripts."""

from __future__ import annotations

import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET

from ..core.models import VideoInfo


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
    subprocess.run(cmd, capture_output=True, text=True, check=True)

    info = _get_video_info(url)
    video_path = os.path.join(output_dir, f"{info['id']}.mp4")
    if not os.path.exists(video_path):
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

    Tries: manual subs → auto-generated subs, across json3 → srv3 → vtt formats.

    Returns a list of segments: [{"start": float, "end": float, "text": str}]
    """
    os.makedirs(output_dir, exist_ok=True)
    sub_path = os.path.join(output_dir, "subs")

    for sub_format in ("json3", "srv3", "vtt"):
        cmd = [
            "yt-dlp",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs", lang,
            "--sub-format", sub_format,
            "--skip-download",
            "--no-playlist",
            "-o", sub_path,
            url,
        ]
        subprocess.run(cmd, capture_output=True, text=True)

        for fname in os.listdir(output_dir):
            if fname.startswith("subs") and fname.endswith(f".{sub_format}"):
                sub_file = os.path.join(output_dir, fname)
                parser = {
                    "json3": _parse_json3_subs,
                    "srv3": _parse_srv3_subs,
                    "vtt": _parse_vtt_subs,
                }[sub_format]
                return _merge_short_segments(parser(sub_file))

    raise RuntimeError(
        f"Could not extract subtitles for language '{lang}'. "
        "The video may not have captions available."
    )


# ---------------------------------------------------------------------------
# Subtitle parsers
# ---------------------------------------------------------------------------

def _parse_json3_subs(filepath: str) -> list[dict]:
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments: list[dict] = []
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
    return segments


def _parse_srv3_subs(filepath: str) -> list[dict]:
    tree = ET.parse(filepath)
    root = tree.getroot()
    segments: list[dict] = []
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
    return segments


def _parse_vtt_subs(filepath: str) -> list[dict]:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    segments: list[dict] = []
    pattern = r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})"
    blocks = re.split(pattern, content)

    i = 1
    while i + 2 < len(blocks):
        start_str, end_str, text_block = blocks[i], blocks[i + 1], blocks[i + 2]
        text = re.sub(r"<[^>]+>", "", text_block).strip()
        text = re.sub(r"\n+", " ", text).strip()
        if text:
            segments.append({
                "start": _vtt_time_to_seconds(start_str),
                "end": _vtt_time_to_seconds(end_str),
                "text": text,
            })
        i += 3
    return segments


def _vtt_time_to_seconds(time_str: str) -> float:
    parts = time_str.split(":")
    h, m = int(parts[0]), int(parts[1])
    s = float(parts[2])
    return h * 3600 + m * 60 + s


def _merge_short_segments(
    segments: list[dict], min_duration: float = 1.0
) -> list[dict]:
    if not segments:
        return segments

    merged = [segments[0].copy()]
    for seg in segments[1:]:
        prev = merged[-1]
        gap = seg["start"] - prev["end"]
        if prev["end"] - prev["start"] < min_duration or gap < 0.1:
            prev["end"] = seg["end"]
            prev["text"] = prev["text"] + " " + seg["text"]
        else:
            merged.append(seg.copy())
    return merged


# ---------------------------------------------------------------------------
# High-level entry point
# ---------------------------------------------------------------------------

def get_video_info(url: str, output_dir: str, source_lang: str = "en") -> VideoInfo:
    """Download video, extract subtitles, and return a VideoInfo object."""
    info = _get_video_info(url)
    video_path = download_video(url, output_dir)
    subtitles = extract_subtitles(url, output_dir, lang=source_lang)

    return VideoInfo(
        video_id=info["id"],
        title=info.get("title", "Untitled"),
        duration=info.get("duration", 0),
        video_path=video_path,
        subtitles=subtitles,
    )
