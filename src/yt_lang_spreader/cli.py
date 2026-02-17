"""Command-line interface for YouTube Language Spreader."""

from __future__ import annotations

import argparse
import sys

from .core.config import PipelineConfig
from .core.pipeline import run_pipeline


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
            "  # Basic: summarize and translate to Chinese (default)\n"
            "  %(prog)s https://youtu.be/abc123\n"
            "\n"
            "  # Use your cloned voice via ElevenLabs\n"
            "  %(prog)s https://youtu.be/abc123 --lang zh \\\n"
            "      --tts elevenlabs --elevenlabs-voice-id YOUR_VOICE_ID\n"
            "\n"
            "  # Use pre-recorded audio files (your own voice)\n"
            "  %(prog)s https://youtu.be/abc123 --lang es \\\n"
            "      --tts local --local-voice-dir ./my_recordings/\n"
            "\n"
            "  # Enable stock chart generation for finance videos\n"
            "  %(prog)s https://youtu.be/abc123 --lang zh --stock-charts\n"
            "\n"
            "  # Low compression, Japanese, 5 segments, no burned-in subs\n"
            "  %(prog)s https://youtu.be/abc123 --lang ja -c 1 -s 5 --no-subtitles\n"
        ),
    )

    # --- Required ---
    parser.add_argument("url", help="YouTube video URL")

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
        "--compression", "-c", type=int, default=3, choices=[1, 2, 3, 4, 5],
        help="Compression level 1-5 (default: 3). 1=detailed, 5=ultra-brief",
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
    oai.add_argument("--model", default="gpt-4o-mini", help="OpenAI model (default: gpt-4o-mini)")

    # --- Output ---
    out = parser.add_argument_group("output")
    out.add_argument("--output", "-o", default="output", help="Output directory (default: output)")
    out.add_argument("--keep-temp", action="store_true", help="Keep temporary files")

    args = parser.parse_args()

    config = PipelineConfig(
        url=args.url,
        source_lang=args.source_lang,
        target_lang=args.lang,
        compression_level=args.compression,
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
        openai_model=args.model,
        output_dir=args.output,
        keep_temp=args.keep_temp,
    )

    try:
        run_pipeline(config)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
