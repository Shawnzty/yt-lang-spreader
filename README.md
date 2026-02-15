# YouTube Language Spreader

Extract narratives from YouTube videos, summarize them with configurable compression, translate to any language, generate voice-over narration, and produce a new video with key screenshots and translated audio.

## Pipeline

```
YouTube URL
  → Download video + extract subtitles
  → Segment transcript into parts
  → Summarize each part (configurable compression 1-5)
  → Translate summaries to target language
  → Generate TTS narration audio
  → Extract key frames from original video
  → Assemble final video with narration + subtitles
```

## Prerequisites

- Python 3.9+
- [ffmpeg](https://ffmpeg.org/) installed and on PATH
- An [OpenAI API key](https://platform.openai.com/api-keys) (for summarization and translation)

## Installation

```bash
pip install -e .
```

Or install dependencies directly:

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Set your OpenAI API key
export OPENAI_API_KEY="sk-..."

# Basic usage: summarize + translate to Chinese
yt-lang-spreader https://youtu.be/VIDEO_ID --lang zh

# Translate to Spanish with detailed summaries (low compression)
yt-lang-spreader https://youtu.be/VIDEO_ID --lang es --compression 1

# Ultra-brief summaries in Japanese, 5 segments, 4 frames each
yt-lang-spreader https://youtu.be/VIDEO_ID --lang ja --compression 5 --segments 5 --frames 4

# Custom output directory, no subtitle overlay
yt-lang-spreader https://youtu.be/VIDEO_ID --lang fr --output my_output --no-subtitles
```

## CLI Options

| Option | Description |
|---|---|
| `url` | YouTube video URL (required) |
| `--lang, -l` | Target language code: zh, es, fr, de, ja, ko, etc. (default: zh) |
| `--compression, -c` | Compression level 1-5 (default: 3). 1=detailed, 5=ultra-brief |
| `--output, -o` | Output directory (default: output) |
| `--segments, -s` | Number of segments (auto-calculated if not set) |
| `--segment-duration` | Target segment duration in seconds (default: 120) |
| `--frames, -f` | Key frames per segment (default: 3) |
| `--no-subtitles` | Don't overlay subtitles on the video |
| `--api-key` | OpenAI API key (or set OPENAI_API_KEY env var) |
| `--model` | OpenAI model (default: gpt-4o-mini) |
| `--keep-temp` | Keep temporary files after processing |

## Compression Levels

| Level | Description | Output Length |
|---|---|---|
| 1 | Detailed - retains most content | ~70-80% of original |
| 2 | Moderate - main points + details | ~50-60% of original |
| 3 | Concise - key points only | ~30-40% of original |
| 4 | Brief - essential takeaways | ~15-25% of original |
| 5 | Ultra-brief - 1-2 sentences | ~5-10% of original |

## Output

The tool generates:
- `<title>_<lang>.mp4` - The final video with key frames and narration
- `<title>_<lang>_metadata.json` - Metadata with all segments, summaries, and translations

## Supported Languages

Any language supported by both OpenAI and Google TTS, including:
zh (Chinese), es (Spanish), fr (French), de (German), ja (Japanese),
ko (Korean), pt (Portuguese), ru (Russian), ar (Arabic), hi (Hindi),
it (Italian), nl (Dutch), pl (Polish), tr (Turkish), vi (Vietnamese), and more.

## Architecture

```
src/yt_lang_spreader/
├── cli.py          # Command-line interface
├── pipeline.py     # End-to-end orchestration
├── downloader.py   # YouTube download + subtitle extraction
├── segmenter.py    # Transcript segmentation
├── summarizer.py   # GPT-based summarization with compression levels
├── translator.py   # GPT-based translation
├── narrator.py     # gTTS text-to-speech generation
└── video_maker.py  # Key frame extraction + video assembly
```
