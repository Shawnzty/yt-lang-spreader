"""Shared data models used across all modules."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VideoInfo:
    """Metadata and paths for a downloaded YouTube video."""

    video_id: str
    title: str
    duration: float  # seconds
    video_path: str
    subtitles: list[dict] = field(default_factory=list)
    transcript_source: str = "youtube_subtitles"
    transcript_language: str = "unknown"
    # [{"start": float, "end": float, "text": str}, ...]


@dataclass
class Segment:
    """A logical segment of the video with its transcript and outputs."""

    index: int
    start: float  # seconds
    end: float  # seconds
    text: str  # original transcript

    # --- Topic classification (set by semantic segmenter) ---
    topic_type: str = ""  # "macro" | "index" | "stock"
    topic_label: str = ""  # e.g. "Fed Meeting", "SP500", "NVDA"
    tickers: list[str] = field(default_factory=list)  # detected tickers
    support_levels: list[float] = field(default_factory=list)
    resistance_levels: list[float] = field(default_factory=list)

    # --- Processing outputs ---
    summary: str = ""
    translated_summary: str = ""

    audio_path: str = ""  # path to narration audio file
    frame_paths: list[str] = field(default_factory=list)  # key frame images
    slide_paths: list[str] = field(default_factory=list)  # generated info slides
    chart_paths: list[str] = field(default_factory=list)  # generated chart images
