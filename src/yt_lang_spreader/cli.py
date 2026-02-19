"""Command-line interface for YouTube Language Spreader."""

from __future__ import annotations

import argparse
import re
import sys

from .core.config import PipelineConfig
from .core.pipeline import resume_pipeline, run_pipeline


def _parse_length(value: str) -> float:
    """Parse a target length string into minutes.

    Accepts formats like: 10, 10min, 10m, 10minutes, 10 min, etc.
    Returns the number as minutes (float).
    """
    value = value.strip()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:min(?:utes?)?|m)?", value)
    if not m:
        raise argparse.ArgumentTypeError(
            f"Invalid length format: '{value}'. "
            "Use a number optionally followed by 'min'/'m'/'minutes', e.g. 10, 10min, 10m, 10minutes"
        )
    return float(m.group(1))


def _add_common_args(parser: argparse.ArgumentParser, url_required: bool = True) -> None:
    """Add all shared arguments to a parser (used by both run and debug)."""

    # --- URL (required for run, optional for debug resume) ---
    if url_required:
        parser.add_argument("url", help="YouTube video URL")
    else:
        parser.add_argument("url", nargs="?", default="", help="YouTube video URL (omit to resume a previous debug run)")

    # --- Language ---
    lang = parser.add_argument_group("language")
    lang.add_argument(
        "--lang", "-l", default="zh",
        help="Target language code (default: zh). e.g. zh, es, fr, de, ja, ko, pt, ru",
    )
    lang.add_argument(
        "--source-lang", default="auto",
        help=(
            "Source subtitle language (default: auto, uses original video language). "
            "If unavailable, audio is transcribed in the video's original language."
        ),
    )

    # --- Summarization ---
    summ = parser.add_argument_group("summarization")
    summ.add_argument(
        "--length", type=_parse_length, default=None,
        help=(
            "Target output video length in minutes. Accepts: 10, 10min, 10m, 10minutes. "
            "If not set, no summarization is performed (full transcript is kept)."
        ),
    )

    # --- Segmentation ---
    seg = parser.add_argument_group("segmentation")
    seg.add_argument(
        "--segments", "-s", type=int, default=None,
        help="Number of segments (auto if not set)",
    )
    seg.add_argument(
        "--segment-duration", type=float, default=120.0,
        help="Target segment duration in seconds (default: 120)",
    )

    # --- TTS / Narration ---
    tts = parser.add_argument_group("narration (TTS)")
    tts.add_argument(
        "--tts", default="gtts",
        choices=["gtts", "elevenlabs", "openai_tts", "local"],
        help="TTS backend (default: gtts). Use 'elevenlabs' for your cloned voice, "
             "'local' for pre-recorded audio files",
    )
    tts.add_argument(
        "--elevenlabs-voice-id", default="",
        help="ElevenLabs voice ID (for cloned voice). Get it from elevenlabs.io/voice-lab",
    )
    tts.add_argument(
        "--elevenlabs-model", default="eleven_multilingual_v2",
        help="ElevenLabs model (default: eleven_multilingual_v2)",
    )
    tts.add_argument(
        "--elevenlabs-api-key", default="",
        help="ElevenLabs API key (or set ELEVENLABS_API_KEY env var)",
    )
    tts.add_argument(
        "--openai-tts-voice", default="alloy",
        help="OpenAI TTS voice (default: alloy). Options: alloy, echo, fable, onyx, nova, shimmer",
    )
    tts.add_argument(
        "--local-voice-dir", default="",
        help="Directory with pre-recorded audio files (narration_001.mp3, etc.)",
    )

    # --- Video ---
    vid = parser.add_argument_group("video output")
    vid.add_argument(
        "--frames", "-f", type=int, default=3,
        help="Key frames per segment (default: 3)",
    )
    vid.add_argument(
        "--no-subtitles", action="store_true",
        help="Do not burn subtitle overlay into the video",
    )
    vid.add_argument(
        "--no-subtitle-files", action="store_true",
        help="Do not generate SRT/VTT subtitle files",
    )

    # --- Plugins ---
    plug = parser.add_argument_group("plugins")
    plug.add_argument(
        "--stock-charts", action="store_true",
        help="Enable stock chart generation for finance/quant videos",
    )
    plug.add_argument(
        "--stock-api", default="longport",
        choices=["longport", "yfinance"],
        help="Stock data API (default: longport). Falls back to yfinance if Longport unavailable.",
    )
    plug.add_argument(
        "--longport-app-key", default="",
        help="Longport app key (or set LONGPORT_APP_KEY env var)",
    )
    plug.add_argument(
        "--longport-app-secret", default="",
        help="Longport app secret (or set LONGPORT_APP_SECRET env var)",
    )
    plug.add_argument(
        "--longport-access-token", default="",
        help="Longport access token (or set LONGPORT_ACCESS_TOKEN env var)",
    )

    # --- OpenAI ---
    oai = parser.add_argument_group("OpenAI")
    oai.add_argument("--api-key", default="", help="OpenAI API key (or set OPENAI_API_KEY)")

    # --- Models ---
    mdl = parser.add_argument_group("models")
    mdl.add_argument(
        "--textmodel", default="gpt-5-mini",
        help="Text model for segmentation, summarization, translation, slides, vision (default: gpt-5-mini)",
    )
    mdl.add_argument(
        "--speechmodel", default="tts-1-hd",
        help="OpenAI TTS model for narration (default: tts-1-hd)",
    )
    mdl.add_argument(
        "--transcriptmodel", default="whisper-1",
        help="Transcription model for audio fallback (default: whisper-1)",
    )

    # --- Output ---
    out = parser.add_argument_group("output")
    out.add_argument("--output", "-o", default="output", help="Output directory (default: output)")
    out.add_argument("--keep-temp", action="store_true", help="Keep temporary files")


def _build_config(args: argparse.Namespace, debug: bool = False) -> PipelineConfig:
    """Build a PipelineConfig from parsed CLI args."""
    return PipelineConfig(
        url=getattr(args, "url", "") or "",
        source_lang=args.source_lang,
        target_lang=args.lang,
        target_length_minutes=args.length,
        num_segments=args.segments,
        segment_duration=args.segment_duration,
        frames_per_segment=args.frames,
        tts_backend=args.tts,
        elevenlabs_voice_id=args.elevenlabs_voice_id,
        elevenlabs_model=args.elevenlabs_model,
        elevenlabs_api_key=args.elevenlabs_api_key,
        openai_tts_voice=args.openai_tts_voice,
        local_voice_dir=args.local_voice_dir,
        generate_subtitles=not args.no_subtitle_files,
        show_subtitles=not args.no_subtitles,
        enable_stock_charts=args.stock_charts,
        stock_api=args.stock_api,
        longport_app_key=args.longport_app_key,
        longport_app_secret=args.longport_app_secret,
        longport_access_token=args.longport_access_token,
        openai_api_key=args.api_key,
        text_model=args.textmodel,
        speech_model=args.speechmodel,
        transcript_model=args.transcriptmodel,
        output_dir=args.output,
        keep_temp=args.keep_temp,
        debug=debug,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="yt-lang-spreader",
        description=(
            "YouTube Language Spreader: Download a YouTube video, extract its "
            "narrative, summarize and translate it, then generate a new video "
            "with key frames and voice-over narration in your chosen language."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Normal run\n"
            "  %(prog)s run https://youtu.be/abc123\n"
            "\n"
            "  # Debug run (new, full pipeline)\n"
            "  %(prog)s debug https://youtu.be/abc123\n"
            "\n"
            "  # Resume a previous debug run interactively\n"
            "  %(prog)s debug\n"
            "\n"
            "  # Summarize to ~10 minutes, Japanese\n"
            "  %(prog)s run https://youtu.be/abc123 --lang ja --length 10min\n"
        ),
    )

    subparsers = parser.add_subparsers(dest="command")

    # --- run subcommand (URL required) ---
    run_parser = subparsers.add_parser(
        "run",
        help="Run the full pipeline (output_YYYYMMDD_NNN/)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_common_args(run_parser, url_required=True)

    # --- debug subcommand (URL optional — omit to resume) ---
    debug_parser = subparsers.add_parser(
        "debug",
        help="Debug mode: with URL starts new run; without URL resumes previous run",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "If no URL is given, lists existing debug runs and lets you\n"
            "resume step-by-step. You can run one step at a time, inspect\n"
            "or edit the intermediate JSON files, then continue.\n"
        ),
    )
    _add_common_args(debug_parser, url_required=False)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == "run":
            config = _build_config(args, debug=False)
            run_pipeline(config)

        elif args.command == "debug":
            config = _build_config(args, debug=True)
            if config.url:
                # New debug run with URL — run full pipeline
                run_pipeline(config)
            else:
                # No URL — resume a previous debug run interactively
                resume_pipeline(config)

    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
