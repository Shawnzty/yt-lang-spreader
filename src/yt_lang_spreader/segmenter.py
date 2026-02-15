"""Segment subtitles into logical parts based on video structure."""

from dataclasses import dataclass


@dataclass
class Segment:
    """A logical segment of the video with its transcript."""

    index: int
    start: float  # seconds
    end: float  # seconds
    text: str
    summary: str = ""
    translated_summary: str = ""


def segment_subtitles(
    subtitles: list[dict],
    duration: float,
    num_segments: int | None = None,
    segment_duration: float | None = None,
) -> list[Segment]:
    """Split subtitles into logical segments.

    Args:
        subtitles: List of subtitle entries with start, end, text.
        duration: Total video duration in seconds.
        num_segments: Number of segments to create. If None, auto-calculated.
        segment_duration: Target duration per segment in seconds. Default ~120s.

    Returns:
        List of Segment objects.
    """
    if not subtitles:
        raise ValueError("No subtitles to segment.")

    if num_segments is None:
        target = segment_duration or 120.0
        num_segments = max(1, round(duration / target))

    # Calculate boundaries based on even time splits
    boundaries = []
    seg_len = duration / num_segments
    for i in range(num_segments):
        boundaries.append((i * seg_len, (i + 1) * seg_len))

    segments = []
    for idx, (seg_start, seg_end) in enumerate(boundaries):
        # Collect subtitle texts that fall within this segment
        texts = []
        actual_start = seg_end  # will be updated
        actual_end = seg_start  # will be updated

        for sub in subtitles:
            # A subtitle belongs to a segment if it overlaps with the boundary
            if sub["end"] > seg_start and sub["start"] < seg_end:
                texts.append(sub["text"])
                actual_start = min(actual_start, sub["start"])
                actual_end = max(actual_end, sub["end"])

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


def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
