"""End-to-end pipeline orchestrating all processing steps."""

import json
import os
import shutil
import tempfile

from .downloader import get_video_info
from .narrator import generate_narration
from .segmenter import Segment, format_timestamp, segment_subtitles
from .summarizer import summarize_segments
from .translator import translate_segments
from .video_maker import create_video, extract_key_frames


def run_pipeline(
    url: str,
    target_lang: str = "zh",
    compression_level: int = 3,
    output_dir: str = "output",
    num_segments: int | None = None,
    segment_duration: float | None = None,
    frames_per_segment: int = 3,
    show_subtitles: bool = True,
    openai_api_key: str | None = None,
    openai_model: str = "gpt-4o-mini",
    keep_temp: bool = False,
) -> str:
    """Run the full processing pipeline.

    Steps:
    1. Download video and extract subtitles
    2. Segment the transcript into parts
    3. Summarize each part (with compression level)
    4. Translate summaries to target language
    5. Generate TTS narration audio
    6. Extract key frames from original video
    7. Assemble final video

    Args:
        url: YouTube video URL.
        target_lang: Target language code (e.g., "zh", "es").
        compression_level: 1 (detailed) to 5 (ultra-brief).
        output_dir: Directory for final output.
        num_segments: Number of segments (auto if None).
        segment_duration: Target segment duration in seconds.
        frames_per_segment: Key frames to extract per segment.
        show_subtitles: Overlay subtitles on the video.
        openai_api_key: OpenAI API key.
        openai_model: OpenAI model name.
        keep_temp: Keep temporary files after processing.

    Returns:
        Path to the output video file.
    """
    os.makedirs(output_dir, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix="yt_lang_spreader_")

    try:
        # Step 1: Download and extract subtitles
        print("\n[1/7] Downloading video and extracting subtitles...")
        video_info = get_video_info(url, os.path.join(tmp_dir, "video"))
        print(f"      Title: {video_info.title}")
        print(f"      Duration: {format_timestamp(video_info.duration)}")
        print(f"      Subtitle segments: {len(video_info.subtitles)}")

        # Step 2: Segment the transcript
        print("\n[2/7] Segmenting transcript into parts...")
        segments = segment_subtitles(
            video_info.subtitles,
            video_info.duration,
            num_segments=num_segments,
            segment_duration=segment_duration,
        )
        print(f"      Created {len(segments)} segments")
        for seg in segments:
            print(
                f"      Part {seg.index}: "
                f"{format_timestamp(seg.start)} - {format_timestamp(seg.end)}"
            )

        # Step 3: Summarize each segment
        print(f"\n[3/7] Summarizing segments (compression level {compression_level})...")
        segments = summarize_segments(
            segments,
            video_info.title,
            compression_level=compression_level,
            api_key=openai_api_key,
            model=openai_model,
        )
        for seg in segments:
            preview = (seg.summary[:80] + "...") if len(seg.summary) > 80 else seg.summary
            print(f"      Part {seg.index}: {preview}")

        # Step 4: Translate summaries
        print(f"\n[4/7] Translating to {target_lang}...")
        segments = translate_segments(
            segments,
            target_lang,
            api_key=openai_api_key,
            model=openai_model,
        )
        for seg in segments:
            preview = (
                (seg.translated_summary[:80] + "...")
                if len(seg.translated_summary) > 80
                else seg.translated_summary
            )
            print(f"      Part {seg.index}: {preview}")

        # Step 5: Generate narration audio
        print(f"\n[5/7] Generating {target_lang} narration audio...")
        audio_dir = os.path.join(tmp_dir, "audio")
        audio_paths = generate_narration(segments, target_lang, audio_dir)
        generated = sum(1 for p in audio_paths if p)
        print(f"      Generated {generated} audio files")

        # Step 6: Extract key frames
        print(f"\n[6/7] Extracting key frames ({frames_per_segment} per segment)...")
        frames_dir = os.path.join(tmp_dir, "frames")
        frame_paths = extract_key_frames(
            video_info.video_path, segments, frames_dir, frames_per_segment
        )
        total_frames = sum(len(f) for f in frame_paths)
        print(f"      Extracted {total_frames} frames")

        # Step 7: Assemble video
        safe_title = "".join(
            c if c.isalnum() or c in " -_" else "_" for c in video_info.title
        )[:50]
        output_filename = f"{safe_title}_{target_lang}.mp4"
        output_path = os.path.join(output_dir, output_filename)

        print(f"\n[7/7] Assembling final video...")
        output_path = create_video(
            segments,
            frame_paths,
            audio_paths,
            output_path,
            target_lang,
            show_subtitles=show_subtitles,
        )
        print(f"      Output: {output_path}")

        # Save metadata
        metadata = {
            "source_url": url,
            "video_title": video_info.title,
            "target_language": target_lang,
            "compression_level": compression_level,
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
            output_dir, output_filename.replace(".mp4", "_metadata.json")
        )
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        print(f"      Metadata: {meta_path}")

        print(f"\nDone! Video saved to: {output_path}")
        return output_path

    finally:
        if not keep_temp:
            shutil.rmtree(tmp_dir, ignore_errors=True)
