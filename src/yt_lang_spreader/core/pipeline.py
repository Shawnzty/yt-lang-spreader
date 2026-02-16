"""End-to-end pipeline orchestrating all processing steps."""

from __future__ import annotations

import json
import os
import shutil
import tempfile

from .config import PipelineConfig
from .models import Segment
from ..extractors.downloader import get_video_info
from ..generators.narrator import generate_narration
from ..generators.subtitles import generate_subtitle_files
from ..generators.video_maker import create_video, extract_key_frames
from ..processors.segmenter import segment_subtitles
from ..processors.summarizer import summarize_segments
from ..processors.translator import translate_segments
from ..utils.formatting import format_timestamp


def run_pipeline(config: PipelineConfig) -> str:
    """Run the full processing pipeline.

    Steps:
    1. Download video and extract subtitles
    2. Segment the transcript into parts
    3. Summarize each part (with compression level)
    4. Translate summaries to target language
    5. Generate TTS narration audio
    6. Extract key frames from original video
    6b. (Optional) Generate stock charts for relevant segments
    7. Generate subtitle files (SRT/VTT) for YouTube CC
    8. Assemble final video

    Returns:
        Path to the output video file.
    """
    config.resolve_api_keys()
    os.makedirs(config.output_dir, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix="yt_lang_spreader_")

    try:
        # Step 1: Download and extract subtitles
        print("\n[1/8] Downloading video and extracting subtitles...")
        video_info = get_video_info(
            config.url,
            os.path.join(tmp_dir, "video"),
            source_lang=config.source_lang,
            openai_api_key=config.openai_api_key,
        )
        print(f"      Title: {video_info.title}")
        print(f"      Duration: {format_timestamp(video_info.duration)}")
        print(f"      Transcript source: {video_info.transcript_source}")
        print(f"      Transcript language: {video_info.transcript_language}")
        print(f"      Subtitle segments: {len(video_info.subtitles)}")

        # Step 2: Segment the transcript
        print("\n[2/8] Segmenting transcript into parts...")
        segments = segment_subtitles(
            video_info.subtitles,
            video_info.duration,
            num_segments=config.num_segments,
            segment_duration=config.segment_duration,
        )
        print(f"      Created {len(segments)} segments")
        for seg in segments:
            print(
                f"      Part {seg.index}: "
                f"{format_timestamp(seg.start)} - {format_timestamp(seg.end)}"
            )

        # Step 3: Summarize each segment
        print(
            f"\n[3/8] Summarizing segments "
            f"(compression level {config.compression_level})..."
        )
        segments = summarize_segments(
            segments,
            video_info.title,
            compression_level=config.compression_level,
            api_key=config.openai_api_key,
            model=config.openai_model,
        )
        for seg in segments:
            preview = (
                (seg.summary[:80] + "...") if len(seg.summary) > 80 else seg.summary
            )
            print(f"      Part {seg.index}: {preview}")

        # Step 4: Translate summaries
        print(f"\n[4/8] Translating to {config.target_lang}...")
        segments = translate_segments(
            segments,
            config.target_lang,
            api_key=config.openai_api_key,
            model=config.openai_model,
        )
        for seg in segments:
            t = seg.translated_summary
            preview = (t[:80] + "...") if len(t) > 80 else t
            print(f"      Part {seg.index}: {preview}")

        # Step 5: Generate narration audio
        print(
            f"\n[5/8] Generating narration audio "
            f"(backend: {config.tts_backend})..."
        )
        audio_dir = os.path.join(tmp_dir, "audio")
        segments = generate_narration(segments, config, audio_dir)
        generated = sum(1 for seg in segments if seg.audio_path)
        print(f"      Generated {generated} audio files")

        # Step 6: Extract key frames
        print(
            f"\n[6/8] Extracting key frames "
            f"({config.frames_per_segment} per segment)..."
        )
        frames_dir = os.path.join(tmp_dir, "frames")
        segments = extract_key_frames(
            video_info.video_path, segments, frames_dir, config.frames_per_segment
        )
        total_frames = sum(len(seg.frame_paths) for seg in segments)
        print(f"      Extracted {total_frames} frames")

        # Step 6b: Stock charts (optional plugin)
        if config.enable_stock_charts:
            print("\n[6b/8] Generating stock charts...")
            from ..plugins.stock_charts import generate_stock_charts

            charts_dir = os.path.join(tmp_dir, "charts")
            segments = generate_stock_charts(segments, charts_dir)
            total_charts = sum(len(seg.chart_paths) for seg in segments)
            print(f"      Generated {total_charts} charts")

        # Step 7: Generate subtitle files for YouTube CC
        safe_title = _safe_filename(video_info.title)
        if config.generate_subtitles:
            print("\n[7/8] Generating subtitle files (SRT/VTT)...")
            sub_base = f"{safe_title}_{config.target_lang}"
            sub_paths = generate_subtitle_files(
                segments,
                config.output_dir,
                formats=config.subtitle_formats,
                base_name=sub_base,
            )
            for p in sub_paths:
                print(f"      {p}")
        else:
            print("\n[7/8] Subtitle file generation skipped")

        # Step 8: Assemble video
        output_filename = f"{safe_title}_{config.target_lang}.mp4"
        output_path = os.path.join(config.output_dir, output_filename)

        print("\n[8/8] Assembling final video...")
        output_path = create_video(
            segments,
            output_path,
            video_size=config.video_size,
            show_subtitles=config.show_subtitles,
        )
        print(f"      Output: {output_path}")

        # Save metadata
        _save_metadata(config, video_info, segments, output_filename)

        print(f"\nDone! Video saved to: {output_path}")
        return output_path

    finally:
        if not config.keep_temp:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _safe_filename(title: str) -> str:
    return "".join(
        c if c.isalnum() or c in " -_" else "_" for c in title
    )[:50].strip()


def _save_metadata(
    config: PipelineConfig,
    video_info,
    segments: list[Segment],
    output_filename: str,
) -> None:
    metadata = {
        "source_url": config.url,
        "video_title": video_info.title,
        "target_language": config.target_lang,
        "compression_level": config.compression_level,
        "tts_backend": config.tts_backend,
        "segments": [
            {
                "index": seg.index,
                "start": seg.start,
                "end": seg.end,
                "original_text": seg.text[:500],
                "summary": seg.summary,
                "translated_summary": seg.translated_summary,
            }
            for seg in segments
        ],
    }
    meta_path = os.path.join(
        config.output_dir, output_filename.replace(".mp4", "_metadata.json")
    )
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(f"      Metadata: {meta_path}")
