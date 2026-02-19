"""Create and manage structured run directories.

Each pipeline run gets a timestamped folder:
  output/output_20260219_001/   (normal mode)
  output/debug_20260219_001/    (debug mode)

Inside, each pipeline step gets its own subfolder:
  step1_download/
  step2_segmentation/
  step3_summarization/
  ...

Intermediate data is saved as JSON so it can be inspected or manually
edited before the next step picks it up.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime


TOTAL_STEPS = 9

STEP_NAMES = {
    1: "download",
    2: "segmentation",
    3: "summarization",
    4: "translation",
    5: "narration",
    6: "keyframes",
    7: "visuals",
    8: "subtitles",
    9: "video",
}


def create_run_dir(output_dir: str, debug: bool = False) -> str:
    """Create a timestamped run directory and return its path.

    Pattern: {output_dir}/{prefix}_{YYYYMMDD}_{NNN}/
    """
    os.makedirs(output_dir, exist_ok=True)
    prefix = "debug" if debug else "output"
    today = datetime.now().strftime("%Y%m%d")
    pattern = f"{prefix}_{today}_"

    existing = [
        d for d in os.listdir(output_dir)
        if os.path.isdir(os.path.join(output_dir, d)) and d.startswith(pattern)
    ]

    max_id = 0
    for d in existing:
        suffix = d[len(pattern):]
        if suffix.isdigit():
            max_id = max(max_id, int(suffix))

    run_id = f"{max_id + 1:03d}"
    run_dir = os.path.join(output_dir, f"{pattern}{run_id}")
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


def find_debug_runs(output_dir: str) -> list[dict]:
    """Find all existing debug run directories.

    Returns a list of dicts sorted by name (most recent last):
      [{"path": "/abs/path", "name": "debug_20260219_001", "last_step": 4}, ...]
    """
    if not os.path.isdir(output_dir):
        return []

    runs = []
    for d in sorted(os.listdir(output_dir)):
        full = os.path.join(output_dir, d)
        if not os.path.isdir(full):
            continue
        if not re.match(r"debug_\d{8}_\d{3}$", d):
            continue
        last = detect_last_completed_step(full)
        runs.append({"path": full, "name": d, "last_step": last})
    return runs


def detect_last_completed_step(run_dir: str) -> int:
    """Detect the highest step that has output files.

    Checks for the key JSON output of each step:
      step1 -> video_info.json
      step2-9 -> segments.json
    Returns 0 if no step is completed.
    """
    for step_num in range(TOTAL_STEPS, 0, -1):
        sd = os.path.join(run_dir, f"step{step_num}_{STEP_NAMES[step_num]}")
        if not os.path.isdir(sd):
            continue
        expected = "video_info.json" if step_num == 1 else "segments.json"
        if os.path.isfile(os.path.join(sd, expected)):
            return step_num
    return 0


def step_dir(run_dir: str, step_num: int) -> str:
    """Return (and create) the directory for a given step number."""
    name = STEP_NAMES.get(step_num, f"step{step_num}")
    path = os.path.join(run_dir, f"step{step_num}_{name}")
    os.makedirs(path, exist_ok=True)
    return path


def save_step_json(run_dir: str, step_num: int, filename: str, data: object) -> str:
    """Save JSON data into a step directory. Returns the path written."""
    d = step_dir(run_dir, step_num)
    path = os.path.join(d, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def load_step_json(run_dir: str, step_num: int, filename: str) -> object:
    """Load JSON data from a step directory.

    This is the entry point for the "edit intermediate files" workflow:
    the user can edit the JSON between runs and the next step will
    pick up the changes.
    """
    d = step_dir(run_dir, step_num)
    path = os.path.join(d, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def segments_to_dicts(segments) -> list[dict]:
    """Serialize a list of Segment dataclasses to JSON-friendly dicts."""
    result = []
    for seg in segments:
        result.append({
            "index": seg.index,
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
            "topic_type": seg.topic_type,
            "topic_label": seg.topic_label,
            "tickers": seg.tickers,
            "support_levels": seg.support_levels,
            "resistance_levels": seg.resistance_levels,
            "summary": seg.summary,
            "translated_summary": seg.translated_summary,
            "audio_path": seg.audio_path,
            "frame_paths": list(seg.frame_paths),
            "slide_paths": list(seg.slide_paths),
            "chart_paths": list(seg.chart_paths),
        })
    return result


def dicts_to_segments(data: list[dict]):
    """Deserialize JSON dicts back into Segment objects."""
    from .models import Segment
    segments = []
    for d in data:
        segments.append(Segment(
            index=d["index"],
            start=d["start"],
            end=d["end"],
            text=d["text"],
            topic_type=d.get("topic_type", ""),
            topic_label=d.get("topic_label", ""),
            tickers=d.get("tickers", []),
            support_levels=d.get("support_levels", []),
            resistance_levels=d.get("resistance_levels", []),
            summary=d.get("summary", ""),
            translated_summary=d.get("translated_summary", ""),
            audio_path=d.get("audio_path", ""),
            frame_paths=d.get("frame_paths", []),
            slide_paths=d.get("slide_paths", []),
            chart_paths=d.get("chart_paths", []),
        ))
    return segments
