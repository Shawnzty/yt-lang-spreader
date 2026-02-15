"""Command-line interface for YouTube Language Spreader."""

import argparse
import sys

from .pipeline import run_pipeline


def main():
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
            "  %(prog)s https://youtu.be/abc123 --lang zh\n"
            "  %(prog)s https://youtu.be/abc123 --lang es --compression 2\n"
            "  %(prog)s https://youtu.be/abc123 --lang ja --segments 5 --frames 4\n"
        ),
    )

    parser.add_argument(
        "url",
        help="YouTube video URL",
    )
    parser.add_argument(
        "--lang", "-l",
        default="zh",
        help=(
            "Target language code (default: zh). "
            "Supported: zh, zh-TW, en, es, fr, de, ja, ko, pt, ru, ar, hi, it, etc."
        ),
    )
    parser.add_argument(
        "--compression", "-c",
        type=int,
        default=3,
        choices=[1, 2, 3, 4, 5],
        help=(
            "Compression level 1-5 (default: 3). "
            "1=detailed (keep ~80%%), 2=moderate (~50%%), 3=concise (~30%%), "
            "4=brief (~20%%), 5=ultra-brief (~10%%)"
        ),
    )
    parser.add_argument(
        "--output", "-o",
        default="output",
        help="Output directory (default: output)",
    )
    parser.add_argument(
        "--segments", "-s",
        type=int,
        default=None,
        help="Number of segments to split the video into (auto if not set)",
    )
    parser.add_argument(
        "--segment-duration",
        type=float,
        default=None,
        help="Target segment duration in seconds (default: 120)",
    )
    parser.add_argument(
        "--frames", "-f",
        type=int,
        default=3,
        help="Number of key frames per segment (default: 3)",
    )
    parser.add_argument(
        "--no-subtitles",
        action="store_true",
        help="Do not overlay subtitles on the output video",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="OpenAI API key (or set OPENAI_API_KEY env var)",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="OpenAI model for summarization/translation (default: gpt-4o-mini)",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary files (downloaded video, frames, audio)",
    )

    args = parser.parse_args()

    try:
        output_path = run_pipeline(
            url=args.url,
            target_lang=args.lang,
            compression_level=args.compression,
            output_dir=args.output,
            num_segments=args.segments,
            segment_duration=args.segment_duration,
            frames_per_segment=args.frames,
            show_subtitles=not args.no_subtitles,
            openai_api_key=args.api_key,
            openai_model=args.model,
            keep_temp=args.keep_temp,
        )
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
