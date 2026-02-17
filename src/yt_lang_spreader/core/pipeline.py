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
from ..generators.slides import generate_slides
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
     2. Semantic segmentation (macro / index / stock topics)
     3. Summarize each segment
     4. Translate summaries to target language
     5. Generate TTS narration audio
     6. Extract key frames from original video
     7. Generate visuals per segment type:
        - macro  → bullet-point info slides
        - index/stock → candlestick charts (with GPT-Vision S/R detection)
     8. Generate subtitle files (SRT/VTT) for YouTube CC
     9. Assemble final video

    Returns:
        Path to the output video file.
    """
    config.resolve_api_keys()
    os.makedirs(config.output_dir, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix="yt_lang_spreader_")

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

    try:
        # Step 1: Download and extract subtitles
        print("\n[1/9] Downloading video and extracting subtitles...")
        video_info = get_video_info(
            config.url,
            os.path.join(tmp_dir, "video"),
            source_lang=config.source_lang,
            openai_api_key=config.openai_api_key,
            transcription_model=config.transcript_model,
        )
        print(f"      Title: {video_info.title}")
        print(f"      Duration: {format_timestamp(video_info.duration)}")
        print(f"      Transcript source: {video_info.transcript_source}")
        print(f"      Transcript language: {video_info.transcript_language}")
        print(f"      Subtitle segments: {len(video_info.subtitles)}")

        # Step 2: Semantic segmentation
        print("\n[2/9] Segmenting transcript by topic (semantic)...")
        segments = segment_subtitles(
            video_info.subtitles,
            video_info.duration,
            num_segments=config.num_segments,
            segment_duration=config.segment_duration,
            api_key=config.openai_api_key,
            model=config.text_model,
            video_title=video_info.title,
        )
        print(f"      Created {len(segments)} segments")
        for seg in segments:
            tickers_str = f" [{', '.join(seg.tickers)}]" if seg.tickers else ""
            sr_str = ""
            if seg.support_levels or seg.resistance_levels:
                sr_str = (
                    f" S:{seg.support_levels} R:{seg.resistance_levels}"
                )
            print(
                f"      Part {seg.index}: [{seg.topic_type}] {seg.topic_label}"
                f"{tickers_str}{sr_str} "
                f"({format_timestamp(seg.start)} - {format_timestamp(seg.end)})"
            )

        # Step 3: Summarize each segment (skip if --length not set)
        if config.target_length_minutes is not None:
            video_duration_min = video_info.duration / 60.0
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
                video_info.title,
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
            print("\n[3/9] No target length set – keeping full transcript")
            for seg in segments:
                seg.summary = seg.text

        # Step 4: Translate summaries
        print(f"\n[4/9] Translating to {config.target_lang}...")
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

        # Step 5: Generate narration audio
        print(
            f"\n[5/9] Generating narration audio "
            f"(backend: {config.tts_backend})..."
        )
        audio_dir = os.path.join(tmp_dir, "audio")
        segments = generate_narration(segments, config, audio_dir)
        generated = sum(1 for seg in segments if seg.audio_path)
        print(f"      Generated {generated} audio files")

        # Step 6: Extract key frames (needed for GPT Vision S/R detection)
        print(
            f"\n[6/9] Extracting key frames "
            f"({config.frames_per_segment} per segment)..."
        )
        frames_dir = os.path.join(tmp_dir, "frames")
        segments = extract_key_frames(
            video_info.video_path, segments, frames_dir, config.frames_per_segment
        )
        total_frames = sum(len(seg.frame_paths) for seg in segments)
        print(f"      Extracted {total_frames} frames")

        # Step 7: Generate visuals per segment type
        print("\n[7/9] Generating visuals by segment type...")
        slides_dir = os.path.join(tmp_dir, "slides")
        charts_dir = os.path.join(tmp_dir, "charts")

        macro_count = 0
        chart_count = 0

        for seg in segments:
            if seg.topic_type == "macro":
                # Generate clean info slides with bullet points
                paths = generate_slides(
                    seg, slides_dir,
                    api_key=config.openai_api_key,
                    model=config.text_model,
                    size=config.video_size,
                )
                seg.slide_paths = paths
                macro_count += len(paths)

            elif seg.topic_type in ("index", "stock") and seg.tickers:
                # Generate candlestick charts (with GPT-Vision S/R refinement)
                from ..plugins.stock_charts import generate_stock_charts

                generate_stock_charts([seg], charts_dir, config)
                chart_count += len(seg.chart_paths)

        print(f"      Macro slides: {macro_count}")
        print(f"      Stock/index charts: {chart_count}")

        # Step 8: Generate subtitle files for YouTube CC
        safe_title = _safe_filename(video_info.title)
        if config.generate_subtitles:
            print("\n[8/9] Generating subtitle files (SRT/VTT)...")
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
            print("\n[8/9] Subtitle file generation skipped")

        # Step 9: Assemble video
        output_filename = f"{safe_title}_{config.target_lang}.mp4"
        output_path = os.path.join(config.output_dir, output_filename)

        print("\n[9/9] Assembling final video...")
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
        "target_length_minutes": config.target_length_minutes,
        "text_model": config.text_model,
        "speech_model": config.speech_model,
        "transcript_model": config.transcript_model,
        "tts_backend": config.tts_backend,
        "stock_api": config.stock_api,
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
        config.output_dir, output_filename.replace(".mp4", "_metadata.json")
    )
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(f"      Metadata: {meta_path}")
