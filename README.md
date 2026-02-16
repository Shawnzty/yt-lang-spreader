# YouTube Language Spreader

Extract narratives from YouTube videos, summarize them with configurable compression, translate to any language, generate voice-over narration **using your own voice**, and produce a new video with key screenshots, stock charts, and translated audio — complete with SRT/VTT subtitles for YouTube CC.

## Pipeline

```
YouTube URL
  → Download video + extract subtitles
  → Segment transcript into parts
  → Summarize each part (configurable compression 1-5)
  → Translate summaries to target language
  → Generate narration audio (gTTS / ElevenLabs voice clone / local recordings)
  → Extract key frames from original video
  → [Optional] Generate stock price charts with support/resistance levels
  → Generate SRT/VTT subtitle files for YouTube CC
  → Assemble final video with narration + subtitles
```

## Prerequisites

- Python 3.9+
- [ffmpeg](https://ffmpeg.org/) installed and on PATH
- An [OpenAI API key](https://platform.openai.com/api-keys) (for summarization and translation)
- (Optional) [ElevenLabs API key](https://elevenlabs.io/) for voice cloning

## Installation

```bash
# Core install
pip install -e .

# With stock chart support
pip install -e ".[stock]"

# With GUI
pip install -e ".[gui]"

# Everything
pip install -e ".[all]"
```

## Quick Start

```bash
export OPENAI_API_KEY="sk-..."

# Basic: summarize + translate to Chinese
yt-lang-spreader https://youtu.be/VIDEO_ID --lang zh
```

## Using Your Own Voice

To avoid AI voice detection on YouTube, you have two options:

### Option A: ElevenLabs Voice Cloning (recommended)

1. Create an account at [elevenlabs.io](https://elevenlabs.io)
2. Go to **Voice Lab** → **Add Generative or Cloned Voice**
3. Upload several samples of your voice (1-5 minutes of clear speech)
4. Copy the **Voice ID** from the voice settings
5. Run:

```bash
export ELEVENLABS_API_KEY="your-key"
yt-lang-spreader https://youtu.be/VIDEO_ID --lang zh \
    --tts elevenlabs --elevenlabs-voice-id YOUR_VOICE_ID
```

### Option B: Pre-recorded Audio (fully manual)

1. Run the pipeline once with `--keep-temp` to see segment boundaries
2. Record yourself narrating each segment, saving as:
   ```
   my_recordings/
   ├── narration_001.mp3
   ├── narration_002.mp3
   └── narration_003.mp3
   ```
3. Re-run with the local backend:

```bash
yt-lang-spreader https://youtu.be/VIDEO_ID --lang es \
    --tts local --local-voice-dir ./my_recordings/
```

## Stock Chart Plugin

For finance/quant analysis videos, enable automatic stock chart generation:

```bash
pip install -e ".[stock]"

yt-lang-spreader https://youtu.be/VIDEO_ID --lang zh --stock-charts
```

This will:
- Auto-detect stock ticker mentions ($AAPL, "ticker NVDA", etc.)
- Find support/resistance levels mentioned in the transcript
- Generate annotated price charts with MA20/MA50, volume, and price level markers
- Insert charts into the video alongside key frames

## YouTube Subtitle Files

By default, the tool generates `.srt` and `.vtt` subtitle files alongside the video. Upload these to YouTube Studio → Subtitles → Add Language → Upload File, so viewers can toggle CC on/off.

To skip subtitle file generation:
```bash
yt-lang-spreader https://youtu.be/VIDEO_ID --lang zh --no-subtitle-files
```

## CLI Options

| Option | Description |
|---|---|
| `url` | YouTube video URL (required) |
| **Language** | |
| `--lang, -l` | Target language code (default: zh) |
| `--source-lang` | Source subtitle language (default: en) |
| **Summarization** | |
| `--compression, -c` | Compression level 1-5 (default: 3) |
| **Segmentation** | |
| `--segments, -s` | Number of segments (auto if not set) |
| `--segment-duration` | Target duration per segment in seconds (default: 120) |
| **Narration** | |
| `--tts` | TTS backend: gtts, elevenlabs, openai_tts, local (default: gtts) |
| `--elevenlabs-voice-id` | ElevenLabs cloned voice ID |
| `--elevenlabs-api-key` | ElevenLabs API key (or ELEVENLABS_API_KEY env) |
| `--elevenlabs-model` | ElevenLabs model (default: eleven_multilingual_v2) |
| `--openai-tts-voice` | OpenAI TTS voice: alloy, echo, fable, onyx, nova, shimmer |
| `--local-voice-dir` | Directory with pre-recorded narration_NNN.mp3 files |
| **Video** | |
| `--frames, -f` | Key frames per segment (default: 3) |
| `--no-subtitles` | Don't burn subtitle overlay into the video |
| `--no-subtitle-files` | Don't generate SRT/VTT files |
| **Plugins** | |
| `--stock-charts` | Enable stock chart generation for finance videos |
| **OpenAI** | |
| `--api-key` | OpenAI API key (or OPENAI_API_KEY env) |
| `--model` | OpenAI model (default: gpt-4o-mini) |
| **Output** | |
| `--output, -o` | Output directory (default: output) |
| `--keep-temp` | Keep temporary files after processing |

## Compression Levels

| Level | Description | Output Length |
|---|---|---|
| 1 | Detailed - retains most content | ~70-80% of original |
| 2 | Moderate - main points + details | ~50-60% of original |
| 3 | Concise - key points only | ~30-40% of original |
| 4 | Brief - essential takeaways | ~15-25% of original |
| 5 | Ultra-brief - 1-2 sentences | ~5-10% of original |

## Output Files

| File | Description |
|---|---|
| `<title>_<lang>.mp4` | Final video with key frames, charts, and narration |
| `<title>_<lang>.srt` | SRT subtitle file for YouTube CC upload |
| `<title>_<lang>.vtt` | VTT subtitle file for YouTube CC upload |
| `<title>_<lang>_metadata.json` | Segments, summaries, and translations |

## Architecture

```
src/yt_lang_spreader/
├── cli.py                      # Command-line interface
├── core/
│   ├── config.py               # Centralized PipelineConfig dataclass
│   ├── models.py               # Shared data models (VideoInfo, Segment)
│   └── pipeline.py             # End-to-end orchestration
├── extractors/
│   └── downloader.py           # YouTube download + subtitle extraction
├── processors/
│   ├── segmenter.py            # Transcript segmentation
│   ├── summarizer.py           # GPT-based summarization (5 compression levels)
│   └── translator.py           # GPT-based translation
├── generators/
│   ├── narrator.py             # Multi-backend TTS (gTTS / ElevenLabs / OpenAI / local)
│   ├── subtitles.py            # SRT & VTT subtitle file generation
│   └── video_maker.py          # Key frame extraction + video assembly
├── plugins/
│   └── stock_charts.py         # Stock price chart plotting with S/R levels
├── gui/
│   ├── __init__.py             # GUI package (reserved for future)
│   └── app.py                  # Gradio web UI scaffold
└── utils/
    └── formatting.py           # Shared text/time formatting helpers
```

## GUI (Preview)

A Gradio-based web UI scaffold is included. To try it:

```bash
pip install -e ".[gui]"
python -m yt_lang_spreader.gui.app
```

## Supported Languages

Any language supported by both OpenAI and Google TTS, including:
zh (Chinese), es (Spanish), fr (French), de (German), ja (Japanese),
ko (Korean), pt (Portuguese), ru (Russian), ar (Arabic), hi (Hindi),
it (Italian), nl (Dutch), pl (Polish), tr (Turkish), vi (Vietnamese), and more.
