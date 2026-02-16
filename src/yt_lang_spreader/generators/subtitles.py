"""Generate SRT and VTT subtitle files for YouTube CC upload.

YouTube accepts .srt and .vtt files for closed captions. These files are
generated from the translated summaries so viewers can toggle CC on/off.
"""

from __future__ import annotations

import os

from ..core.models import Segment


def generate_subtitle_files(
    segments: list[Segment],
    output_dir: str,
    formats: list[str] | None = None,
    base_name: str = "subtitles",
) -> list[str]:
    """Generate subtitle files in SRT and/or VTT format.

    Each segment's translated_summary (or summary as fallback) is placed
    at the segment's time range. When a segment has narration audio, the
    subtitle duration is estimated from the audio; otherwise the segment
    time boundaries are used.

    Args:
        segments: List of Segment objects with text/summaries.
        output_dir: Directory to save subtitle files.
        formats: List of formats to generate ("srt", "vtt"). Default: both.
        base_name: Base filename (without extension).

    Returns:
        List of paths to generated subtitle files.
    """
    if formats is None:
        formats = ["srt", "vtt"]

    os.makedirs(output_dir, exist_ok=True)
    paths: list[str] = []

    # Build the subtitle entries
    entries = _build_subtitle_entries(segments)

    if "srt" in formats:
        srt_path = os.path.join(output_dir, f"{base_name}.srt")
        _write_srt(entries, srt_path)
        paths.append(srt_path)

    if "vtt" in formats:
        vtt_path = os.path.join(output_dir, f"{base_name}.vtt")
        _write_vtt(entries, vtt_path)
        paths.append(vtt_path)

    return paths


def _build_subtitle_entries(segments: list[Segment]) -> list[dict]:
    """Build subtitle entries with proper timing.

    Each segment's text is split into smaller chunks to display
    as readable subtitle lines (YouTube recommends ≤2 lines, ≤42 chars each).
    """
    entries: list[dict] = []
    sub_index = 1

    for segment in segments:
        text = segment.translated_summary or segment.summary
        if not text:
            continue

        # Split text into chunks suitable for subtitle display
        chunks = _split_into_subtitle_chunks(text, max_chars_per_chunk=84)
        seg_duration = segment.end - segment.start
        chunk_duration = seg_duration / len(chunks) if chunks else seg_duration

        for i, chunk in enumerate(chunks):
            start = segment.start + i * chunk_duration
            end = start + chunk_duration

            entries.append({
                "index": sub_index,
                "start": start,
                "end": end,
                "text": chunk,
            })
            sub_index += 1

    return entries


def _split_into_subtitle_chunks(
    text: str, max_chars_per_chunk: int = 84
) -> list[str]:
    """Split text into subtitle-sized chunks (roughly 2 lines × 42 chars).

    Tries to break at sentence boundaries first, then at word boundaries.
    """
    # First split at sentence boundaries
    sentences: list[str] = []
    current = ""
    for char in text:
        current += char
        if char in ".!?。！？" and len(current.strip()) > 0:
            sentences.append(current.strip())
            current = ""
    if current.strip():
        sentences.append(current.strip())

    # Now group sentences into chunks
    chunks: list[str] = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 <= max_chars_per_chunk:
            current_chunk = (
                f"{current_chunk} {sentence}" if current_chunk else sentence
            )
        else:
            if current_chunk:
                chunks.append(current_chunk)
            # If a single sentence is too long, split by words
            if len(sentence) > max_chars_per_chunk:
                chunks.extend(_split_long_sentence(sentence, max_chars_per_chunk))
            else:
                current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk)

    return chunks if chunks else [text[:max_chars_per_chunk]]


def _split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    """Split a long sentence by word boundaries."""
    words = sentence.split()
    chunks: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current = f"{current} {word}" if current else word
        else:
            if current:
                chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def _write_srt(entries: list[dict], path: str) -> None:
    """Write SRT subtitle file."""
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(f"{entry['index']}\n")
            f.write(
                f"{_format_srt_time(entry['start'])} --> "
                f"{_format_srt_time(entry['end'])}\n"
            )
            f.write(f"{entry['text']}\n\n")


def _write_vtt(entries: list[dict], path: str) -> None:
    """Write WebVTT subtitle file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for entry in entries:
            f.write(
                f"{_format_vtt_time(entry['start'])} --> "
                f"{_format_vtt_time(entry['end'])}\n"
            )
            f.write(f"{entry['text']}\n\n")


def _format_srt_time(seconds: float) -> str:
    """Format time for SRT: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_vtt_time(seconds: float) -> str:
    """Format time for VTT: HH:MM:SS.mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
