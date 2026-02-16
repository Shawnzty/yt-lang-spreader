"""Download YouTube videos and extract subtitles/transcripts."""

from __future__ import annotations

import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET

from openai import OpenAI

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


def _get_attr_or_key(obj, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _get_media_duration(path: str) -> float:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=nokey=1:noprint_wrappers=1",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return 0.0
    try:
        return float(result.stdout.strip())
    except (TypeError, ValueError):
        return 0.0


def _segment_audio_for_transcription(
    video_path: str,
    output_dir: str,
    segment_seconds: int = 600,
) -> list[str]:
    chunk_dir = os.path.join(output_dir, "audio_chunks")
    os.makedirs(chunk_dir, exist_ok=True)
    output_pattern = os.path.join(chunk_dir, "chunk_%03d.mp3")
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "mp3",
        "-f", "segment",
        "-segment_time", str(segment_seconds),
        "-y",
        output_pattern,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        stderr = result.stderr.strip().splitlines()[-1] if result.stderr else ""
        raise RuntimeError(
            "Failed to extract audio for transcription. "
            f"Please ensure ffmpeg is installed. {stderr}"
        )

    chunk_paths = sorted(
        os.path.join(chunk_dir, f)
        for f in os.listdir(chunk_dir)
        if f.startswith("chunk_") and f.endswith(".mp3")
    )
    if not chunk_paths:
        raise RuntimeError("No audio chunks were produced for transcription.")
    return chunk_paths


def _segments_from_transcription(
    transcription,
    chunk_start: float,
    fallback_end: float,
) -> list[dict]:
    raw_segments = _get_attr_or_key(transcription, "segments", [])
    segments: list[dict] = []

    for seg in raw_segments or []:
        text = _get_attr_or_key(seg, "text", "")
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        start = float(_get_attr_or_key(seg, "start", 0.0)) + chunk_start
        end = float(_get_attr_or_key(seg, "end", 0.0)) + chunk_start
        if end <= start:
            end = start + 0.5
        segments.append({"start": start, "end": end, "text": text})

    if segments:
        return segments

    text = _get_attr_or_key(transcription, "text", "")
    text = re.sub(r"\s+", " ", str(text)).strip()
    if not text:
        return []
    return [{"start": chunk_start, "end": fallback_end, "text": text}]


def transcribe_narrative(
    video_path: str,
    output_dir: str,
    api_key: str,
    model: str = "whisper-1",
    segment_seconds: int = 600,
) -> tuple[list[dict], str]:
    """Transcribe audio directly when no YouTube subtitles are available."""
    if not api_key:
        raise RuntimeError(
            "No subtitles available and OPENAI_API_KEY is missing. "
            "Set OPENAI_API_KEY to enable fallback transcription."
        )

    chunk_paths = _segment_audio_for_transcription(
        video_path, output_dir, segment_seconds=segment_seconds
    )
    client = OpenAI(api_key=api_key)
    all_segments: list[dict] = []
    detected_language = ""

    for i, chunk_path in enumerate(chunk_paths):
        chunk_start = i * segment_seconds
        chunk_duration = _get_media_duration(chunk_path)
        fallback_end = chunk_start + max(chunk_duration, 1.0)

        with open(chunk_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model=model,
                file=audio_file,
                response_format="verbose_json",
                temperature=0,
            )

        if not detected_language:
            detected_language = str(
                _get_attr_or_key(transcription, "language", "")
            ).strip()
        all_segments.extend(
            _segments_from_transcription(
                transcription=transcription,
                chunk_start=chunk_start,
                fallback_end=fallback_end,
            )
        )

    if not all_segments:
        raise RuntimeError("Fallback transcription produced no text.")

    all_segments.sort(key=lambda s: s["start"])
    return _merge_short_segments(all_segments), (detected_language or "unknown")


def _resolve_source_subtitle_language(info: dict, source_lang: str) -> str:
    requested = (source_lang or "").strip()
    if requested and requested.lower() != "auto":
        return requested

    original_lang = (info.get("language") or "").strip()
    subtitles = info.get("subtitles") or {}
    auto_subtitles = info.get("automatic_captions") or {}
    available_langs = list(dict.fromkeys([
        *subtitles.keys(),
        *auto_subtitles.keys(),
    ]))
    if not available_langs:
        return original_lang or "en"

    if original_lang:
        if original_lang in available_langs:
            return original_lang

        original_base = original_lang.split("-", 1)[0]
        for lang in available_langs:
            if lang == original_base or lang.startswith(original_base + "-"):
                return lang

    return available_langs[0]


# ---------------------------------------------------------------------------
# High-level entry point
# ---------------------------------------------------------------------------

def get_video_info(
    url: str,
    output_dir: str,
    source_lang: str = "auto",
    openai_api_key: str = "",
    transcription_model: str = "whisper-1",
) -> VideoInfo:
    """Download video and return transcript from subtitles or audio transcription."""
    info = _get_video_info(url)
    video_path = download_video(url, output_dir)
    subtitle_lang = _resolve_source_subtitle_language(info, source_lang)
    transcript_source = "youtube_subtitles"
    transcript_language = subtitle_lang

    try:
        subtitles = extract_subtitles(url, output_dir, lang=subtitle_lang)
    except RuntimeError:
        subtitles, detected_language = transcribe_narrative(
            video_path,
            output_dir,
            api_key=openai_api_key,
            model=transcription_model,
        )
        transcript_source = "audio_transcription"
        transcript_language = detected_language

    return VideoInfo(
        video_id=info["id"],
        title=info.get("title", "Untitled"),
        duration=info.get("duration", 0),
        video_path=video_path,
        subtitles=subtitles,
        transcript_source=transcript_source,
        transcript_language=transcript_language,
    )
