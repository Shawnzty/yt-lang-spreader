"""Segment subtitles into logical parts based on video structure."""

from __future__ import annotations

from ..core.models import Segment


def segment_subtitles(
    subtitles: list[dict],
    duration: float,
    num_segments: int | None = None,
    segment_duration: float = 120.0,
) -> list[Segment]:
    """Split subtitles into logical segments.

    Args:
        subtitles: List of subtitle entries with start, end, text.
        duration: Total video duration in seconds.
        num_segments: Number of segments to create. If None, auto-calculated.
        segment_duration: Target duration per segment in seconds.

    Returns:
        List of Segment objects.
    """
    if not subtitles:
        raise ValueError("No subtitles to segment.")

    if num_segments is None:
        num_segments = max(1, round(duration / segment_duration))

    seg_len = duration / num_segments
    segments: list[Segment] = []

    for idx in range(num_segments):
        seg_start = idx * seg_len
        seg_end = (idx + 1) * seg_len

        texts = []
        for sub in subtitles:
            if sub["end"] > seg_start and sub["start"] < seg_end:
                texts.append(sub["text"])

        combined_text = " ".join(texts).strip()
        if not combined_text:
            combined_text = "(No narration in this segment)"

        segments.append(Segment(
            index=idx + 1,
            start=seg_start,
            end=seg_end,
            text=combined_text,
        ))

    return segments
