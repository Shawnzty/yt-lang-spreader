"""End-to-end pipeline orchestrating all processing steps."""

from __future__ import annotations

import json
import os
import shutil

from .config import PipelineConfig
from .models import Segment
from .requirements import ensure_runtime_requirements
from .run_dir import (
    create_run_dir,
    dicts_to_segments,
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


def run_pipeline(config: PipelineConfig) -> str:
    """Run the full processing pipeline.

    Each step saves its output to a structured folder:
      {run_dir}/step1_download/
      {run_dir}/step2_segmentation/
      ...

    In debug mode the folder is named debug_YYYYMMDD_NNN instead of
    output_YYYYMMDD_NNN.  Intermediate JSON files can be edited between
    runs to override any step's output.

    Returns:
        Path to the output video file.
    """
    config.resolve_api_keys()
    ensure_runtime_requirements(config)

    run = create_run_dir(config.output_dir, debug=config.debug)
    mode_label = "DEBUG" if config.debug else "OUTPUT"
    print(f"\n{'=' * 50}")
    print(f"  {mode_label} RUN: {run}")
    print(f"{'=' * 50}")

    # Print models in use
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

    # Save config for reproducibility
    save_step_json(run, 0, "config.json", {
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
    })
    # Rename step0 dir to something clearer
    s0 = step_dir(run, 0)
    config_dir = os.path.join(run, "step0_config")
    if os.path.exists(s0) and not os.path.exists(config_dir):
        os.rename(s0, config_dir)

    # ------------------------------------------------------------------
    # Step 1: Download video and extract subtitles
    # ------------------------------------------------------------------
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

    # Save step 1 output
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

    # ------------------------------------------------------------------
    # Step 2: Semantic segmentation
    # ------------------------------------------------------------------
    s2 = step_dir(run, 2)
    print("\n[2/9] Segmenting transcript by topic (semantic)...")

    # Load step 1 output (allows user edits to subtitles)
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

    # ------------------------------------------------------------------
    # Step 3: Summarize each segment
    # ------------------------------------------------------------------
    s3 = step_dir(run, 3)

    # Load step 2 output (allows user edits to segments)
    segments = dicts_to_segments(load_step_json(run, 2, "segments.json"))

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

    # ------------------------------------------------------------------
    # Step 4: Translate summaries
    # ------------------------------------------------------------------
    s4 = step_dir(run, 4)
    print(f"\n[4/9] Translating to {config.target_lang}...")

    # Load step 3 output (allows user edits to summaries)
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

    # ------------------------------------------------------------------
    # Step 5: Generate narration audio
    # ------------------------------------------------------------------
    s5 = step_dir(run, 5)
    print(
        f"\n[5/9] Generating narration audio "
        f"(backend: {config.tts_backend})..."
    )

    # Load step 4 output (allows user edits to translations)
    segments = dicts_to_segments(load_step_json(run, 4, "segments.json"))

    segments = generate_narration(segments, config, s5)
    generated = sum(1 for seg in segments if seg.audio_path)
    print(f"      Generated {generated} audio files")

    save_step_json(run, 5, "segments.json", segments_to_dicts(segments))
    print(f"      Saved: {s5}")

    # ------------------------------------------------------------------
    # Step 6: Extract key frames from original video
    # ------------------------------------------------------------------
    s6 = step_dir(run, 6)
    print(
        f"\n[6/9] Extracting key frames "
        f"({config.frames_per_segment} per segment)..."
    )

    # Load step 5 output
    segments = dicts_to_segments(load_step_json(run, 5, "segments.json"))

    segments = extract_key_frames(
        video_info.video_path, segments, s6, config.frames_per_segment
    )
    total_frames = sum(len(seg.frame_paths) for seg in segments)
    print(f"      Extracted {total_frames} frames")

    save_step_json(run, 6, "segments.json", segments_to_dicts(segments))
    print(f"      Saved: {s6}")

    # ------------------------------------------------------------------
    # Step 7: Generate visuals per segment type
    # ------------------------------------------------------------------
    s7 = step_dir(run, 7)
    print("\n[7/9] Generating visuals by segment type...")

    # Load step 6 output (allows user edits to frame_paths)
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

    # ------------------------------------------------------------------
    # Step 8: Generate subtitle files for YouTube CC
    # ------------------------------------------------------------------
    s8 = step_dir(run, 8)

    # Load step 7 output
    segments = dicts_to_segments(load_step_json(run, 7, "segments.json"))

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

    # ------------------------------------------------------------------
    # Step 9: Assemble final video
    # ------------------------------------------------------------------
    s9 = step_dir(run, 9)

    # Load step 8 output (allows user edits to slide/chart/audio paths)
    segments = dicts_to_segments(load_step_json(run, 8, "segments.json"))

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

    # Save final metadata
    _save_metadata(config, vi_data, segments, s9, output_filename)

    print(f"\n{'=' * 50}")
    print(f"  Run complete: {run}")
    print(f"  Video: {output_path}")
    print(f"{'=' * 50}")
    return output_path


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
