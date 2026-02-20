"""End-to-end pipeline orchestrating all processing steps."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime
from typing import TextIO

from .config import PipelineConfig
from .models import Segment
from .requirements import ensure_runtime_requirements
from .run_dir import (
    STEP_NAMES,
    TOTAL_STEPS,
    create_run_dir,
    dicts_to_segments,
    find_debug_runs,
    load_step_json,
    save_step_json,
    segments_to_dicts,
    step_dir,
)
from ..extractors.downloader import get_video_info
from ..generators.narrator import generate_narration
from ..generators.slides import generate_slides
from ..generators.subtitles import generate_subtitle_files
from ..generators.video_maker import create_video, extract_key_frames
from ..processors.segmenter import segment_subtitles
from ..processors.summarizer import summarize_segments
from ..processors.translator import translate_segments
from ..utils.formatting import format_timestamp


_STEP_TIMINGS_FILE = "step_timings.json"
_TERMINAL_OUTPUT_FILE = "terminal_output.log"
_RUN_REPORT_FILE = "run_report.txt"


class _TeeStream:
    """Write to terminal and file at the same time."""

    def __init__(self, terminal: TextIO, file_stream: TextIO) -> None:
        self._terminal = terminal
        self._file_stream = file_stream

    def write(self, data: str) -> int:
        self._terminal.write(data)
        self._file_stream.write(data)
        return len(data)

    def flush(self) -> None:
        self._terminal.flush()
        self._file_stream.flush()

    def isatty(self) -> bool:
        return bool(getattr(self._terminal, "isatty", lambda: False)())

    @property
    def encoding(self) -> str:
        return getattr(self._terminal, "encoding", "utf-8")


# ======================================================================
# Individual step functions
# ======================================================================

def _step1_download(run: str, config: PipelineConfig) -> None:
    """Step 1: Download video and extract subtitles."""
    s1 = step_dir(run, 1)
    print("\n[1/9] Downloading video and extracting subtitles...")
    video_info = get_video_info(
        config.url,
        s1,
        source_lang=config.source_lang,
        openai_api_key=config.openai_api_key,
        transcription_model=config.transcript_model,
    )
    print(f"      Title: {video_info.title}")
    print(f"      Duration: {format_timestamp(video_info.duration)}")
    print(f"      Transcript source: {video_info.transcript_source}")
    print(f"      Transcript language: {video_info.transcript_language}")
    print(f"      Subtitle segments: {len(video_info.subtitles)}")

    save_step_json(run, 1, "video_info.json", {
        "video_id": video_info.video_id,
        "title": video_info.title,
        "duration": video_info.duration,
        "video_path": video_info.video_path,
        "transcript_source": video_info.transcript_source,
        "transcript_language": video_info.transcript_language,
        "subtitles": video_info.subtitles,
    })
    print(f"      Saved: {s1}")


def _step2_segmentation(run: str, config: PipelineConfig) -> None:
    """Step 2: Semantic segmentation."""
    s2 = step_dir(run, 2)
    print("\n[2/9] Segmenting transcript by topic (semantic)...")

    vi_data = load_step_json(run, 1, "video_info.json")

    segments = segment_subtitles(
        vi_data["subtitles"],
        vi_data["duration"],
        num_segments=config.num_segments,
        segment_duration=config.segment_duration,
        api_key=config.openai_api_key,
        model=config.text_model,
        video_title=vi_data["title"],
    )
    print(f"      Created {len(segments)} segments")
    for seg in segments:
        tickers_str = f" [{', '.join(seg.tickers)}]" if seg.tickers else ""
        sr_str = ""
        if seg.support_levels or seg.resistance_levels:
            sr_str = f" S:{seg.support_levels} R:{seg.resistance_levels}"
        print(
            f"      Part {seg.index}: [{seg.topic_type}] {seg.topic_label}"
            f"{tickers_str}{sr_str} "
            f"({format_timestamp(seg.start)} - {format_timestamp(seg.end)})"
        )

    save_step_json(run, 2, "segments.json", segments_to_dicts(segments))
    print(f"      Saved: {s2}")


def _step3_summarization(run: str, config: PipelineConfig) -> None:
    """Step 3: Summarize each segment."""
    s3 = step_dir(run, 3)

    segments = dicts_to_segments(load_step_json(run, 2, "segments.json"))
    vi_data = load_step_json(run, 1, "video_info.json")

    if config.target_length_minutes is not None:
        video_duration_min = vi_data["duration"] / 60.0
        compression_ratio = min(
            config.target_length_minutes / video_duration_min, 1.0
        ) if video_duration_min > 0 else 1.0
        print(
            f"\n[3/9] Summarizing segments "
            f"(target ~{config.target_length_minutes:.0f}min from "
            f"{video_duration_min:.0f}min, ratio {compression_ratio:.0%})..."
        )
        segments = summarize_segments(
            segments,
            vi_data["title"],
            compression_ratio=compression_ratio,
            api_key=config.openai_api_key,
            model=config.text_model,
        )
        for seg in segments:
            preview = (
                (seg.summary[:80] + "...") if len(seg.summary) > 80 else seg.summary
            )
            print(f"      Part {seg.index}: {preview}")
    else:
        print("\n[3/9] No target length set - keeping full transcript")
        for seg in segments:
            seg.summary = seg.text

    save_step_json(run, 3, "segments.json", segments_to_dicts(segments))
    print(f"      Saved: {s3}")


def _step4_translation(run: str, config: PipelineConfig) -> None:
    """Step 4: Translate summaries."""
    s4 = step_dir(run, 4)
    print(f"\n[4/9] Translating to {config.target_lang}...")

    segments = dicts_to_segments(load_step_json(run, 3, "segments.json"))

    segments = translate_segments(
        segments,
        config.target_lang,
        api_key=config.openai_api_key,
        model=config.text_model,
    )
    for seg in segments:
        t = seg.translated_summary
        preview = (t[:80] + "...") if len(t) > 80 else t
        print(f"      Part {seg.index}: {preview}")

    save_step_json(run, 4, "segments.json", segments_to_dicts(segments))
    print(f"      Saved: {s4}")


def _step5_narration(run: str, config: PipelineConfig) -> None:
    """Step 5: Generate narration audio."""
    s5 = step_dir(run, 5)
    print(
        f"\n[5/9] Generating narration audio "
        f"(backend: {config.tts_backend})..."
    )

    segments = dicts_to_segments(load_step_json(run, 4, "segments.json"))

    segments = generate_narration(segments, config, s5)
    generated = sum(1 for seg in segments if seg.audio_path)
    print(f"      Generated {generated} audio files")

    save_step_json(run, 5, "segments.json", segments_to_dicts(segments))
    print(f"      Saved: {s5}")


def _step6_keyframes(run: str, config: PipelineConfig) -> None:
    """Step 6: Extract key frames from original video."""
    s6 = step_dir(run, 6)
    print(
        f"\n[6/9] Extracting key frames "
        f"({config.frames_per_segment} per segment)..."
    )

    segments = dicts_to_segments(load_step_json(run, 5, "segments.json"))
    vi_data = load_step_json(run, 1, "video_info.json")

    segments = extract_key_frames(
        vi_data["video_path"], segments, s6, config.frames_per_segment
    )
    total_frames = sum(len(seg.frame_paths) for seg in segments)
    print(f"      Extracted {total_frames} frames")

    save_step_json(run, 6, "segments.json", segments_to_dicts(segments))
    print(f"      Saved: {s6}")


def _step7_visuals(run: str, config: PipelineConfig) -> None:
    """Step 7: Generate visuals per segment type."""
    s7 = step_dir(run, 7)
    print("\n[7/9] Generating visuals by segment type...")

    segments = dicts_to_segments(load_step_json(run, 6, "segments.json"))

    slides_dir = os.path.join(s7, "slides")
    charts_dir = os.path.join(s7, "charts")
    macro_count = 0
    chart_count = 0

    for seg in segments:
        if seg.topic_type == "macro":
            paths = generate_slides(
                seg, slides_dir,
                api_key=config.openai_api_key,
                model=config.text_model,
                target_lang=config.target_lang,
                size=config.video_size,
            )
            seg.slide_paths = paths
            macro_count += len(paths)

        elif seg.topic_type in ("index", "stock") and seg.tickers:
            from ..plugins.stock_charts import generate_stock_charts

            generate_stock_charts([seg], charts_dir, config)
            chart_count += len(seg.chart_paths)

    print(f"      Macro slides: {macro_count}")
    print(f"      Stock/index charts: {chart_count}")

    save_step_json(run, 7, "segments.json", segments_to_dicts(segments))
    print(f"      Saved: {s7}")


def _step8_subtitles(run: str, config: PipelineConfig) -> None:
    """Step 8: Generate subtitle files for YouTube CC."""
    s8 = step_dir(run, 8)

    segments = dicts_to_segments(load_step_json(run, 7, "segments.json"))
    vi_data = load_step_json(run, 1, "video_info.json")
    safe_title = _safe_filename(vi_data["title"])

    if config.generate_subtitles:
        print("\n[8/9] Generating subtitle files (SRT/VTT)...")
        sub_base = f"{safe_title}_{config.target_lang}"
        sub_paths = generate_subtitle_files(
            segments,
            s8,
            formats=config.subtitle_formats,
            base_name=sub_base,
        )
        for p in sub_paths:
            print(f"      {p}")
    else:
        print("\n[8/9] Subtitle file generation skipped")

    save_step_json(run, 8, "segments.json", segments_to_dicts(segments))
    print(f"      Saved: {s8}")


def _step9_video(run: str, config: PipelineConfig) -> str:
    """Step 9: Assemble final video. Returns output path."""
    s9 = step_dir(run, 9)

    segments = dicts_to_segments(load_step_json(run, 8, "segments.json"))
    vi_data = load_step_json(run, 1, "video_info.json")
    safe_title = _safe_filename(vi_data["title"])

    output_filename = f"{safe_title}_{config.target_lang}.mp4"
    output_path = os.path.join(s9, output_filename)

    print("\n[9/9] Assembling final video...")
    output_path = create_video(
        segments,
        output_path,
        video_size=config.video_size,
        show_subtitles=config.show_subtitles,
        target_lang=config.target_lang,
    )
    print(f"      Output: {output_path}")

    _save_metadata(config, vi_data, segments, s9, output_filename)
    return output_path


# Step dispatch table
_STEP_FUNCS = {
    1: _step1_download,
    2: _step2_segmentation,
    3: _step3_summarization,
    4: _step4_translation,
    5: _step5_narration,
    6: _step6_keyframes,
    7: _step7_visuals,
    8: _step8_subtitles,
    9: _step9_video,
}


# ======================================================================
# Pipeline entry points
# ======================================================================

def _print_models(config: PipelineConfig) -> None:
    print("\n=== Models in use ===")
    print(f"  Text model       : {config.text_model}")
    print(f"                     (segmentation, summarization, translation, slides, vision)")
    print(f"  Speech model     : {config.speech_model}")
    print(f"                     (OpenAI TTS narration)")
    print(f"  Transcript model : {config.transcript_model}")
    print(f"                     (audio transcription fallback)")
    if config.tts_backend == "elevenlabs":
        print(f"  ElevenLabs model : {config.elevenlabs_model}")
        print(f"                     (voice cloning narration)")
    print("=====================")


def _step0_config_dir(run: str) -> str:
    config_dir = os.path.join(run, "step0_config")
    legacy_dir = os.path.join(run, "step0_step0")
    if os.path.isdir(legacy_dir):
        os.makedirs(config_dir, exist_ok=True)
        for name in os.listdir(legacy_dir):
            src = os.path.join(legacy_dir, name)
            dst = os.path.join(config_dir, name)
            if not os.path.exists(dst):
                shutil.move(src, dst)
        if not os.listdir(legacy_dir):
            os.rmdir(legacy_dir)
    os.makedirs(config_dir, exist_ok=True)
    return config_dir


def _format_target_length(target_length_minutes: float | None) -> str:
    if target_length_minutes is None:
        return "original length"
    if float(target_length_minutes).is_integer():
        return f"{int(target_length_minutes)}min"
    return f"{target_length_minutes:.1f}min"


def _print_requested_output(config: PipelineConfig) -> None:
    print("\n=== Requested output ===")
    print(f"  Target language : {config.target_lang}")
    print(f"  Output length   : {_format_target_length(config.target_length_minutes)}")
    print("========================")


def _prompt_target_language() -> str:
    while True:
        value = input("Target language code (e.g. ja): ").strip()
        if value:
            return value
        print("  Please enter a language code.")


def _save_config_snapshot(run: str, config: PipelineConfig) -> None:
    config_path = os.path.join(_step0_config_dir(run), "config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({
            "url": config.url,
            "source_lang": config.source_lang,
            "target_lang": config.target_lang,
            "target_length_minutes": config.target_length_minutes,
            "text_model": config.text_model,
            "speech_model": config.speech_model,
            "transcript_model": config.transcript_model,
            "tts_backend": config.tts_backend,
            "stock_api": config.stock_api,
            "debug": config.debug,
        }, f, ensure_ascii=False, indent=2)


def _load_step_timings(run: str) -> dict[int, float]:
    path = os.path.join(_step0_config_dir(run), _STEP_TIMINGS_FILE)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}

    steps: dict[int, float] = {}
    for item in raw.get("steps", []):
        try:
            step_num = int(item["step"])
            seconds = float(item["seconds"])
        except (KeyError, TypeError, ValueError):
            continue
        if step_num in STEP_NAMES:
            steps[step_num] = seconds
    return steps


def _save_step_timings(run: str, step_timings: dict[int, float]) -> str:
    path = os.path.join(_step0_config_dir(run), _STEP_TIMINGS_FILE)
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "total_seconds": round(sum(step_timings.values()), 3),
        "steps": [
            {
                "step": step_num,
                "name": STEP_NAMES[step_num],
                "seconds": round(step_timings[step_num], 3),
            }
            for step_num in sorted(step_timings)
            if step_num in STEP_NAMES
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes = int(seconds // 60)
    remaining = seconds - (minutes * 60)
    if minutes < 60:
        return f"{minutes}m {remaining:04.1f}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins:02d}m {remaining:04.1f}s"


def _print_timing_summary(step_timings: dict[int, float]) -> None:
    if not step_timings:
        return
    print("\n=== Step timings ===")
    for step_num in sorted(step_timings):
        if step_num not in STEP_NAMES:
            continue
        print(f"  Step {step_num} ({STEP_NAMES[step_num]}): {_format_elapsed(step_timings[step_num])}")
    print(f"  Total measured : {_format_elapsed(sum(step_timings.values()))}")
    print("====================")


@contextmanager
def _capture_terminal_output(run: str):
    log_path = os.path.join(_step0_config_dir(run), _TERMINAL_OUTPUT_FILE)
    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write(
            f"\n===== Session {datetime.now().isoformat(timespec='seconds')} =====\n"
        )
        log_file.flush()
        tee_stdout = _TeeStream(sys.stdout, log_file)
        tee_stderr = _TeeStream(sys.stderr, log_file)
        with redirect_stdout(tee_stdout), redirect_stderr(tee_stderr):
            yield


def _write_run_report(run: str, step_timings: dict[int, float]) -> str:
    step0 = _step0_config_dir(run)
    report_path = os.path.join(step0, _RUN_REPORT_FILE)
    terminal_log_path = os.path.join(step0, _TERMINAL_OUTPUT_FILE)

    terminal_output = ""
    if os.path.isfile(terminal_log_path):
        with open(terminal_log_path, "r", encoding="utf-8") as f:
            terminal_output = f.read()

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("Step timings\n")
        f.write("============\n")
        for step_num in sorted(step_timings):
            if step_num not in STEP_NAMES:
                continue
            f.write(
                f"Step {step_num} ({STEP_NAMES[step_num]}): "
                f"{_format_elapsed(step_timings[step_num])}\n"
            )
        f.write(f"Total measured: {_format_elapsed(sum(step_timings.values()))}\n\n")
        f.write("Terminal output\n")
        f.write("===============\n")
        f.write(terminal_output)
    return report_path


def run_pipeline(config: PipelineConfig) -> str:
    """Run the full pipeline from step 1 through step 9.

    Creates a new timestamped run directory.
    Returns path to the output video file.
    """
    config.resolve_api_keys()
    ensure_runtime_requirements(config)

    run = create_run_dir(config.output_dir, debug=config.debug)
    step_timings = _load_step_timings(run)
    try:
        with _capture_terminal_output(run):
            mode_label = "DEBUG" if config.debug else "OUTPUT"
            print(f"\n{'=' * 50}")
            print(f"  {mode_label} RUN: {run}")
            print(f"{'=' * 50}")

            _print_models(config)
            _print_requested_output(config)
            _save_config_snapshot(run, config)

            # Execute all steps
            _run_steps(
                run,
                config,
                from_step=1,
                to_step=TOTAL_STEPS,
                step_timings=step_timings,
            )
            _print_timing_summary(step_timings)

            print(f"\n{'=' * 50}")
            print(f"  Run complete: {run}")
            print(f"{'=' * 50}")
    finally:
        _save_config_snapshot(run, config)
        _save_step_timings(run, step_timings)
        _write_run_report(run, step_timings)
    return run


def resume_pipeline(config: PipelineConfig) -> str:
    """Resume a previous debug run interactively.

    1. Lists existing debug folders, lets user pick one (or auto-selects
       if there's only one).
    2. Detects the last completed step.
    3. Asks: run next step only, or complete all remaining steps.
    4. After each single step, asks again.

    Returns the run directory path.
    """
    config.resolve_api_keys()
    ensure_runtime_requirements(config)

    # --- Find debug runs ---
    runs = find_debug_runs(config.output_dir)
    if not runs:
        print(f"\nNo debug runs found in '{config.output_dir}/'.")
        print("Start a new debug run with: yt-lang-spreader debug <URL>")
        return ""

    # --- Select run ---
    if len(runs) == 1:
        selected = runs[0]
        print(f"\nFound 1 debug run: {selected['name']}")
    else:
        print(f"\nFound {len(runs)} debug runs:\n")
        for i, r in enumerate(runs, 1):
            last = r["last_step"]
            step_label = (
                f"step {last}/{TOTAL_STEPS} ({STEP_NAMES[last]})"
                if last > 0 else "no steps completed"
            )
            print(f"  [{i}] {r['name']}  — {step_label}")
        print()

        while True:
            choice = input("Select run to resume (number): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(runs):
                selected = runs[int(choice) - 1]
                break
            print(f"  Please enter a number between 1 and {len(runs)}.")

    run = selected["path"]
    last_step = selected["last_step"]
    step_timings = _load_step_timings(run)
    try:
        with _capture_terminal_output(run):
            print(f"\n{'=' * 50}")
            print(f"  RESUMING DEBUG RUN: {selected['name']}")
            print(f"  Last completed step: {last_step}/{TOTAL_STEPS}", end="")
            if last_step > 0:
                print(f" ({STEP_NAMES[last_step]})")
            else:
                print()
            print(f"{'=' * 50}")

            if last_step >= TOTAL_STEPS:
                print("\nAll steps are already complete. Nothing to resume.")
                _print_timing_summary(step_timings)
                return run

            # --- Load config from the run if URL not provided ---
            config_path = os.path.join(run, "step0_config", "config.json")
            if os.path.isfile(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    saved_cfg = json.load(f)
                if not config.url and saved_cfg.get("url"):
                    config.url = saved_cfg["url"]
                if not config.target_lang and saved_cfg.get("target_lang"):
                    config.target_lang = saved_cfg["target_lang"]
                if config.target_length_minutes is None and saved_cfg.get("target_length_minutes") is not None:
                    config.target_length_minutes = saved_cfg["target_length_minutes"]

            if not config.target_lang:
                config.target_lang = _prompt_target_language()

            _print_models(config)
            _print_requested_output(config)
            _save_config_snapshot(run, config)

            # --- Interactive step execution ---
            next_step = last_step + 1
            while next_step <= TOTAL_STEPS:
                remaining = TOTAL_STEPS - next_step + 1
                next_name = STEP_NAMES[next_step]

                print(f"\nNext: step {next_step}/{TOTAL_STEPS} ({next_name})")
                print(f"Remaining steps: {remaining}")
                print()
                print(f"  [1] Run next step only (step {next_step}: {next_name})")
                print(f"  [2] Complete all remaining steps ({next_step}-{TOTAL_STEPS})")
                print(f"  [3] Quit")
                print()

                while True:
                    choice = input("Choice: ").strip()
                    if choice in ("1", "2", "3"):
                        break
                    print("  Please enter 1, 2, or 3.")

                if choice == "3":
                    _print_timing_summary(step_timings)
                    print(f"\nPaused at step {next_step}. Resume later with: yt-lang-spreader debug")
                    return run

                if choice == "2":
                    # Run all remaining
                    _run_steps(
                        run,
                        config,
                        from_step=next_step,
                        to_step=TOTAL_STEPS,
                        step_timings=step_timings,
                    )
                    _print_timing_summary(step_timings)
                    print(f"\n{'=' * 50}")
                    print(f"  Run complete: {run}")
                    print(f"{'=' * 50}")
                    return run

                # choice == "1": run single step
                _run_steps(
                    run,
                    config,
                    from_step=next_step,
                    to_step=next_step,
                    step_timings=step_timings,
                )
                _print_timing_summary(step_timings)
                next_step += 1

            print(f"\n{'=' * 50}")
            print(f"  Run complete: {run}")
            print(f"{'=' * 50}")
    finally:
        _save_config_snapshot(run, config)
        _save_step_timings(run, step_timings)
        _write_run_report(run, step_timings)
    return run


def _run_steps(
    run: str,
    config: PipelineConfig,
    from_step: int,
    to_step: int,
    step_timings: dict[int, float] | None = None,
) -> None:
    """Execute pipeline steps in the given range [from_step, to_step]."""
    if step_timings is None:
        step_timings = {}
    for step_num in range(from_step, to_step + 1):
        func = _STEP_FUNCS[step_num]
        started = time.perf_counter()
        failed = False
        try:
            func(run, config)
        except Exception:
            failed = True
            raise
        finally:
            elapsed = time.perf_counter() - started
            step_timings[step_num] = elapsed
            status = " (failed)" if failed else ""
            print(f"      Step runtime: {_format_elapsed(elapsed)}{status}")
            _save_step_timings(run, step_timings)


# ======================================================================
# Helpers
# ======================================================================

def _safe_filename(title: str) -> str:
    return "".join(
        c if c.isalnum() or c in " -_" else "_" for c in title
    )[:50].strip()


def _save_metadata(
    config: PipelineConfig,
    vi_data: dict,
    segments: list[Segment],
    output_dir: str,
    output_filename: str,
) -> None:
    metadata = {
        "source_url": config.url,
        "video_title": vi_data["title"],
        "target_language": config.target_lang,
        "target_length_minutes": config.target_length_minutes,
        "text_model": config.text_model,
        "speech_model": config.speech_model,
        "transcript_model": config.transcript_model,
        "tts_backend": config.tts_backend,
        "stock_api": config.stock_api,
        "debug": config.debug,
        "segments": [
            {
                "index": seg.index,
                "start": seg.start,
                "end": seg.end,
                "topic_type": seg.topic_type,
                "topic_label": seg.topic_label,
                "tickers": seg.tickers,
                "support_levels": seg.support_levels,
                "resistance_levels": seg.resistance_levels,
                "original_text": seg.text[:500],
                "summary": seg.summary,
                "translated_summary": seg.translated_summary,
            }
            for seg in segments
        ],
    }
    meta_path = os.path.join(
        output_dir, output_filename.replace(".mp4", "_metadata.json")
    )
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(f"      Metadata: {meta_path}")
