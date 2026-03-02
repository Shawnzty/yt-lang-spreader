# YouTube Language Spreader

Download YouTube videos, extract transcripts, summarize with configurable compression, translate to any language, generate voice-over narration (including your own cloned voice), and produce a new video with key frames, stock charts, and translated audio — complete with SRT/VTT subtitles for YouTube CC.

Built for a specific use case: re-creating finance YouTuber videos in another language, preserving the original structure (macro overview → index analysis → individual stock breakdowns).

## Pipeline (9 Steps)

```
YouTube URL
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ Step 1: Download          extractors/downloader.py  │  Download video + extract subtitles (Whisper fallback)
│ Step 2: Segmentation      processors/segmenter.py   │  Split transcript by topic (macro/index/stock)
│ Step 3: Summarization     processors/summarizer.py  │  Summarize each segment (ratio-based compression)
│ Step 4: Translation       processors/translator.py  │  Translate summaries to target language
│ Step 5: Narration         generators/narrator.py    │  Generate TTS audio per segment
│ Step 6: Key Frames        generators/video_maker.py │  Extract frames from original video
│ Step 7: Visuals           generators/slides.py      │  Generate info slides (macro) & charts (stock/index)
│                           plugins/stock_charts.py   │
│ Step 8: Subtitles         generators/subtitles.py   │  Generate SRT/VTT for YouTube CC
│ Step 9: Video Assembly    generators/video_maker.py │  Combine visuals + audio into final MP4
└─────────────────────────────────────────────────────┘
  │
  ▼
output/output_YYYYMMDD_NNN/step9_video/<title>_<lang>.mp4
```

### Step Details

| Step | Name | LLM | What it does |
|------|------|-----|-------------|
| 1 | **Download** | Whisper (fallback) | Downloads video via yt-dlp. Extracts subtitles (json3 → srv3 → vtt). If no subs available, transcribes audio with Whisper in 10-min chunks. Saves `video_info.json`. |
| 2 | **Segmentation** | GPT (1 call) | Sends full timestamped transcript to GPT. Identifies topic boundaries and classifies each as `macro`, `index`, or `stock`. Extracts tickers and support/resistance levels. Saves `segments.json`. |
| 3 | **Summarization** | GPT (1 call/segment) | Summarizes each segment as narration text. Compression ratio auto-calculated from `--length` / video duration. If no `--length`, copies full transcript. Saves `segments.json`. |
| 4 | **Translation** | GPT (1 call/segment) | Translates each segment's summary to the target language. Maintains spoken tone for voice-over. Saves `segments.json`. |
| 5 | **Narration** | TTS API | Generates speech audio (MP3) from translated text using chosen backend: gTTS, ElevenLabs, OpenAI TTS, or local recordings. Saves `narration_NNN.mp3` files + `segments.json`. |
| 6 | **Key Frames** | None | Extracts still frames from the original video using ffmpeg. Distributes frames evenly across each segment's time range. Saves `frame_NNN_NN.jpg` files + `segments.json`. |
| 7 | **Visuals** | GPT (slides) + GPT Vision (charts) | **Macro segments**: GPT extracts bullet points → renders Pillow slides. **Index/stock segments**: GPT Vision reads S/R from video screenshots → fetches OHLCV data → plots candlestick charts. Saves to `slides/` and `charts/` + `segments.json`. |
| 8 | **Subtitles** | None | Splits translated text into YouTube-sized chunks (max 84 chars). Generates `.srt` and `.vtt` files. Saves `segments.json`. |
| 9 | **Video** | None | Assembles final video with moviepy. Routes visuals by topic type (slides for macro, charts for stock/index, frames as fallback). Overlays subtitles. Encodes H.264 + AAC @ 24fps. Saves `.mp4` + `_metadata.json`. |

### Step Data Flow

Each step saves its output to `stepN_name/` and the next step loads from it:

```
step1_download/video_info.json
       ↓
step2_segmentation/segments.json    ← loads step1 (subtitles, duration, title)
       ↓
step3_summarization/segments.json   ← loads step2 (segments) + step1 (duration)
       ↓
step4_translation/segments.json     ← loads step3 (summary)
       ↓
step5_narration/segments.json       ← loads step4 (translated_summary)
       ↓
step6_keyframes/segments.json       ← loads step5 (segments) + step1 (video_path)
       ↓
step7_visuals/segments.json         ← loads step6 (frame_paths, tickers)
       ↓
step8_subtitles/segments.json       ← loads step7 (segments) + step1 (title)
       ↓
step9_video/                        ← loads step8 (all paths) + step1 (title)
```

You can manually edit any `segments.json` between steps and the next step will pick up your changes.

## Prerequisites

- Python 3.9+
- [ffmpeg](https://ffmpeg.org/) installed and on PATH
- [OpenAI API key](https://platform.openai.com/api-keys) — for summarization, translation, and fallback transcription
- (Optional) [ElevenLabs API key](https://elevenlabs.io/) — for voice cloning

## Installation

```bash
pip install -e .
```

Dependencies are checked on every run. If any are missing, the CLI prints what's needed and offers to install them.

```bash
# Or install manually:
pip install -r requirements.txt
```

## Quick Start

```bash
export OPENAI_API_KEY="sk-..."

# Basic: translate to Chinese, keep full length
yt-lang-spreader run https://youtu.be/VIDEO_ID --lang zh

# Summarize to ~10 minutes
yt-lang-spreader run https://youtu.be/VIDEO_ID --lang zh --length 10min

# Debug mode: run full pipeline with inspectable intermediate files
yt-lang-spreader debug https://youtu.be/VIDEO_ID --lang ja --length 5min

# Resume a previous debug run step-by-step
yt-lang-spreader debug
```

You can also put API keys in a `.env` file (auto-loaded):
```
OPENAI_API_KEY="sk-..."
ELEVENLABS_API_KEY="..."
LONGPORT_APP_KEY="..."
```

## Commands

### `yt-lang-spreader run <URL> [options]`

Runs the full 9-step pipeline. Creates `output/output_YYYYMMDD_NNN/`.

### `yt-lang-spreader debug [URL] [options]`

- **With URL**: Starts a new debug run. Creates `output/debug_YYYYMMDD_NNN/`. Identical pipeline, different folder prefix.
- **Without URL**: Resumes a previous debug run. Lists existing debug folders, lets you select one, then asks: run next step only, or complete all remaining? After each single step, prompts again. This lets you inspect/edit intermediate JSON between steps.

## CLI Options

| Option | Description | Default |
|---|---|---|
| **Language** | | |
| `--lang, -l` | Target language code (prompted if not set) | _(interactive)_ |
| `--source-lang` | Source subtitle language | `auto` |
| **Summarization** | | |
| `--length` | Target output length: `10`, `10min`, `10m`, `10minutes` | _(none = full)_ |
| **Segmentation** | | |
| `--segments, -s` | Number of segments | _(auto)_ |
| `--segment-duration` | Target segment duration in seconds | `120` |
| **Narration** | | |
| `--tts` | Backend: `gtts`, `elevenlabs`, `openai_tts`, `local` | `gtts` |
| `--elevenlabs-voice-id` | ElevenLabs cloned voice ID | |
| `--elevenlabs-model` | ElevenLabs model | `eleven_multilingual_v2` |
| `--elevenlabs-api-key` | ElevenLabs API key (or env `ELEVENLABS_API_KEY`) | |
| `--openai-tts-voice` | OpenAI TTS voice: alloy, echo, fable, onyx, nova, shimmer | `alloy` |
| `--local-voice-dir` | Directory with pre-recorded `narration_NNN.mp3` files | |
| **Video** | | |
| `--frames, -f` | Key frames per segment | `3` |
| `--no-subtitles` | Don't burn subtitle overlay into video | |
| `--no-subtitle-files` | Don't generate SRT/VTT files | |
| **Models** | | |
| `--textmodel` | Text/vision model (segmentation, summarization, translation, slides) | `gpt-5-mini` |
| `--speechmodel` | TTS model (OpenAI narration) | `tts-1-hd` |
| `--transcriptmodel` | Transcription model (audio fallback) | `whisper-1` |
| **Plugins** | | |
| `--stock-charts` | Enable stock chart generation | `false` |
| `--stock-api` | Stock data source: `longport`, `yfinance` | `longport` |
| `--longport-app-key` | Longport app key (or env `LONGPORT_APP_KEY`) | |
| `--longport-app-secret` | Longport app secret (or env `LONGPORT_APP_SECRET`) | |
| `--longport-access-token` | Longport access token (or env `LONGPORT_ACCESS_TOKEN`) | |
| **OpenAI** | | |
| `--api-key` | OpenAI API key (or env `OPENAI_API_KEY`) | |
| **Output** | | |
| `--output, -o` | Output directory | `output` |
| `--keep-temp` | Keep temporary files | |

## Using Your Own Voice

### Option A: ElevenLabs Voice Cloning (recommended)

1. Create an account at [elevenlabs.io](https://elevenlabs.io)
2. Go to **Voice Lab** → **Add Generative or Cloned Voice**
3. Upload samples of your voice (1-5 minutes of clear speech)
4. Copy the **Voice ID** from voice settings
5. Run:

```bash
export ELEVENLABS_API_KEY="your-key"
yt-lang-spreader run https://youtu.be/VIDEO_ID --lang zh \
    --tts elevenlabs --elevenlabs-voice-id YOUR_VOICE_ID
```

### Option B: Pre-recorded Audio

1. Run the pipeline once to see segment boundaries
2. Record yourself narrating each segment:
   ```
   my_recordings/narration_001.mp3
   my_recordings/narration_002.mp3
   my_recordings/narration_003.mp3
   ```
3. Re-run with local backend:

```bash
yt-lang-spreader run https://youtu.be/VIDEO_ID --lang es \
    --tts local --local-voice-dir ./my_recordings/
```

## Stock Chart Plugin

For finance videos, enable automatic candlestick chart generation:

```bash
yt-lang-spreader run https://youtu.be/VIDEO_ID --lang zh --stock-charts
```

This will:
- Auto-detect stock tickers mentioned in the transcript (NVDA, AAPL, SPY, etc.)
- Extract support/resistance levels from transcript and video screenshots (GPT Vision)
- Fetch OHLCV data from Longport API (default) or yfinance (fallback)
- Plot candlestick charts with MA5/MA20/MA60, volume bars, and S/R annotations
- Insert charts into the video for index/stock segments

## Skills System (LLM Prompt Customization)

The `skills/` folder contains one markdown file per pipeline step. Each file has an `## Instructions` section where you can write custom instructions that get injected into the LLM prompts for that step.

```
skills/
├── step1_download.md        # Whisper transcription settings
├── step2_segmentation.md    # How to classify topics, handle ambiguity
├── step3_summarization.md   # Narration tone, detail priorities
├── step4_translation.md     # Terminology, formality, jargon handling
├── step5_narration.md       # Voice/speed preferences (future)
├── step6_keyframes.md       # Frame selection rules (future)
├── step7_visuals.md         # Slide style, chart period, S/R formatting
├── step8_subtitles.md       # Subtitle formatting rules (future)
└── step9_video.md           # Assembly preferences (future)
```

Steps currently wired to load skill instructions: **2 (segmentation), 3 (summarization), 4 (translation), 7 (visuals/charts)**. The remaining steps have skill files ready for when LLM capabilities are added.

Example — edit `skills/step2_segmentation.md`:
```markdown
## Instructions
- Always create a separate segment for semiconductor-related discussion
- Classify SOXX/SOX as "index" not "stock"
- The youtuber always starts with 5 minutes of macro, then indices, then stocks
```

## Output Structure

```
output/output_20260302_001/
├── step0_config/config.json             # Snapshot of run configuration
├── step1_download/
│   ├── video_info.json                  # Video metadata + subtitle list
│   └── VIDEO_ID.mp4                     # Downloaded video
├── step2_segmentation/
│   └── segments.json                    # Topic-segmented transcript
├── step3_summarization/
│   └── segments.json                    # + summary field per segment
├── step4_translation/
│   └── segments.json                    # + translated_summary field
├── step5_narration/
│   ├── segments.json                    # + audio_path field
│   ├── narration_001.mp3
│   ├── narration_002.mp3
│   └── ...
├── step6_keyframes/
│   ├── segments.json                    # + frame_paths field
│   ├── frame_001_00.jpg
│   ├── frame_001_01.jpg
│   └── ...
├── step7_visuals/
│   ├── segments.json                    # + slide_paths, chart_paths fields
│   ├── slides/slide_001_00.png
│   ├── charts/chart_003_NVDA.png
│   └── ...
├── step8_subtitles/
│   ├── segments.json
│   ├── <title>_<lang>.srt
│   └── <title>_<lang>.vtt
└── step9_video/
    ├── <title>_<lang>.mp4               # Final video
    └── <title>_<lang>_metadata.json     # Full run metadata
```

## Supported Languages

Any language supported by both OpenAI and Google TTS:

zh (Chinese), zh-TW (Traditional Chinese), en (English), es (Spanish), fr (French), de (German), ja (Japanese), ko (Korean), pt (Portuguese), ru (Russian), ar (Arabic), hi (Hindi), it (Italian), nl (Dutch), pl (Polish), tr (Turkish), vi (Vietnamese), th (Thai), sv (Swedish)

---

## Project Structure (for developers / AI coding tools)

> This section serves as a guide for Claude Code, Codex, or any AI tool working on this codebase. It explains what each folder and file does, so you know where to make changes.

```
yt-lang-spreader/
├── README.md                            # This file
├── pyproject.toml                       # Package metadata, dependencies, entry point
├── requirements.txt                     # Flat dependency list for pip install
├── skills/                              # Per-step LLM instruction files (see Skills section)
│   └── stepN_<name>.md
│
└── src/yt_lang_spreader/
    ├── __init__.py                      # Package version (0.3.0)
    ├── cli.py                           # CLI entry point, argument parsing, subcommands
    │
    ├── core/                            # Shared infrastructure
    │   ├── config.py                    # PipelineConfig dataclass (all settings)
    │   ├── models.py                    # VideoInfo + Segment dataclasses
    │   ├── pipeline.py                  # Pipeline orchestration (run_pipeline, resume_pipeline)
    │   ├── run_dir.py                   # Timestamped run directory + step folder management
    │   └── requirements.py             # Runtime dependency checker
    │
    ├── extractors/                      # Step 1: get data from external sources
    │   └── downloader.py               # yt-dlp download, subtitle parsing, Whisper fallback
    │
    ├── processors/                      # Steps 2-4: text processing via LLM
    │   ├── segmenter.py                # Semantic segmentation (macro/index/stock classification)
    │   ├── summarizer.py               # Ratio-based summarization
    │   └── translator.py               # Translation to target language
    │
    ├── generators/                      # Steps 5-9: produce output files
    │   ├── narrator.py                 # TTS audio generation (4 backends)
    │   ├── slides.py                   # Info slide rendering (Pillow) for macro segments
    │   ├── subtitles.py                # SRT/VTT subtitle file generation
    │   └── video_maker.py             # Key frame extraction + final video assembly (moviepy)
    │
    ├── plugins/                         # Optional feature modules
    │   └── stock_charts.py             # Candlestick chart plotting + GPT Vision S/R detection
    │
    ├── gui/                             # Reserved for future web UI
    │   └── app.py                      # Gradio scaffold (not yet connected)
    │
    └── utils/                           # Shared helpers
        ├── fonts.py                    # CJK-safe font loading for Pillow
        ├── formatting.py               # Time/text formatting (format_timestamp, wrap_text)
        ├── openai_compat.py            # GPT-5 compatibility layer (parameter mapping)
        └── skills.py                   # Skill instruction loader from markdown files
```

### File-by-File Reference

#### `cli.py` — Command-line interface
- **Entry point**: `main()` → registered as `yt-lang-spreader` console script
- **Subcommands**: `run` (normal) and `debug` (inspectable)
- `_parse_length()` — parse flexible length formats (10, 10min, 10m, 10minutes)
- `_add_common_args()` — shared argument definitions for both subcommands
- `_build_config()` — construct `PipelineConfig` from parsed args
- `_resolve_interactive_run_options()` — prompt for missing `--lang` and `--length`
- **To modify**: Add new CLI options here, then wire them into `_build_config()` and `PipelineConfig`

#### `core/config.py` — PipelineConfig
- Single dataclass holding every configurable setting
- `resolve_api_keys()` — loads from env vars and `.env` file
- **To modify**: Add new config fields here. Update `_build_config()` in cli.py. Update `_save_config_snapshot()` in pipeline.py.

#### `core/models.py` — Data models
- `VideoInfo` — video metadata from download step
- `Segment` — the central data structure that flows through steps 2-9, accumulating fields at each step
- **To modify**: Add new fields to Segment. Update `segments_to_dicts()` and `dicts_to_segments()` in run_dir.py.

#### `core/pipeline.py` — Pipeline orchestration
- `_step1_download()` through `_step9_video()` — individual step functions
- `_STEP_FUNCS` — dispatch table mapping step numbers to functions
- `_run_steps()` — execute a range of steps
- `run_pipeline()` — create new run dir, execute all 9 steps
- `resume_pipeline()` — interactive debug resume (menu selection, step-by-step)
- `_print_models()` — display model list at start
- `_save_config_snapshot()` — save config to step0_config/
- **To modify**: Add new steps by creating a function, adding to `_STEP_FUNCS`, incrementing `TOTAL_STEPS` in run_dir.py, adding to `STEP_NAMES`.

#### `core/run_dir.py` — Run directory management
- `TOTAL_STEPS`, `STEP_NAMES` — step registry
- `create_run_dir()` — creates `output_YYYYMMDD_NNN/` or `debug_YYYYMMDD_NNN/`
- `find_debug_runs()` — scans for existing debug folders
- `detect_last_completed_step()` — checks which steps have output files
- `save_step_json()` / `load_step_json()` — JSON persistence per step
- `segments_to_dicts()` / `dicts_to_segments()` — Segment serialization
- **To modify**: When adding fields to Segment, update both serialization functions here.

#### `core/requirements.py` — Runtime dependency checker
- `ensure_runtime_requirements()` — checks all required packages are installed
- Prints missing packages with estimated download size, prompts to install

#### `extractors/downloader.py` — YouTube download + subtitles
- `get_video_info()` — high-level entry: download video + get transcript
- `download_video()` — yt-dlp video download
- `extract_subtitles()` — try subtitle formats in order
- `transcribe_narrative()` — Whisper fallback (chunks audio → Whisper API)
- Subtitle parsers: `_parse_json3_subs()`, `_parse_srv3_subs()`, `_parse_vtt_subs()`

#### `processors/segmenter.py` — Semantic segmentation
- `segment_subtitles()` — entry point, tries GPT then falls back to time-based
- `_segment_semantic()` — GPT call with financial topic classification
- `_segment_time_based()` — even time interval fallback
- `_SEGMENTATION_SYSTEM_PROMPT` — system prompt for GPT (editable via skills/step2)
- Loads `skills/step2_segmentation.md` instructions

#### `processors/summarizer.py` — Summarization
- `summarize_segments()` — summarize each segment with compression ratio
- `_build_compression_instruction()` — generates GPT instruction from ratio (6 tiers)
- Loads `skills/step3_summarization.md` instructions

#### `processors/translator.py` — Translation
- `translate_segments()` — translate summaries to target language
- `LANGUAGE_NAMES` — code → full name mapping (20 languages)
- Loads `skills/step4_translation.md` instructions

#### `generators/narrator.py` — TTS audio generation
- `generate_narration()` — dispatcher to backend
- `_generate_gtts()` — Google TTS (free, robotic)
- `_generate_elevenlabs()` — ElevenLabs API with voice cloning
- `_generate_openai_tts()` — OpenAI TTS API (uses `speech_model`)
- `_load_local_recordings()` — copy pre-recorded files

#### `generators/slides.py` — Info slide generation
- `extract_bullet_points()` — GPT extracts structured slide data
- `generate_slides()` — entry point, GPT or fallback
- `_render_slide()` — Pillow rendering (dark navy theme)
- `_fallback_slides()` — sentence splitting when GPT unavailable
- Loads `skills/step7_visuals.md` instructions

#### `generators/subtitles.py` — SRT/VTT generation
- `generate_subtitle_files()` — generates both formats
- `_build_subtitle_entries()` — splits text into YouTube-sized chunks (84 char max)

#### `generators/video_maker.py` — Frame extraction + video assembly
- `extract_key_frames()` — ffmpeg frame extraction at calculated timestamps
- `create_video()` — final assembly with moviepy
- `_select_images_for_segment()` — routing: macro→slides, stock→charts, fallback→frames
- `_create_text_only_clip()` — fallback when no images available
- `_create_subtitle_clip()` — subtitle overlay bar

#### `plugins/stock_charts.py` — Candlestick charts
- `generate_stock_charts()` — entry point for index/stock segments
- `_refine_levels_from_frames()` — GPT Vision reads S/R from video screenshots
- `_fetch_ohlcv()` — dispatcher (Longport → yfinance fallback)
- `_fetch_longport()` / `_fetch_yfinance()` — data fetching
- `_plot_candlestick()` — matplotlib chart with candlesticks, MAs, S/R lines, volume
- Loads `skills/step7_visuals.md` instructions

#### `utils/skills.py` — Skill instruction loader
- `load_skill_instructions(step_num)` — reads `## Instructions` section from `skills/stepN_*.md`
- Strips HTML comment lines, returns empty string if no real content

#### `utils/openai_compat.py` — GPT-5 compatibility
- `chat_completion_params()` — adapts API params for GPT-5 family (no custom temperature, max_completion_tokens mapping)

#### `utils/fonts.py` — Font loading
- `is_cjk_language()` — detect CJK languages needing special fonts
- `get_font()` — cross-platform font loading with CJK fallbacks

#### `utils/formatting.py` — Text/time helpers
- `format_timestamp()` — seconds → "HH:MM:SS" or "MM:SS"
- `format_time_short()` — seconds → "MM:SS"
- `wrap_text()` — word wrap at character limit

### Data Models

#### VideoInfo (from step 1)
```
video_id         str          YouTube video ID
title            str          Video title
duration         float        Duration in seconds
video_path       str          Path to downloaded .mp4
subtitles        list[dict]   [{"start": float, "end": float, "text": str}, ...]
transcript_source str         "youtube_subtitles" | "audio_transcription"
transcript_language str       Detected language code
```

#### Segment (flows through steps 2-9)
```
index                 int          Segment number (1-based)
start                 float        Start time in seconds
end                   float        End time in seconds
text                  str          Original transcript text

topic_type            str          "macro" | "index" | "stock"        ← set by step 2
topic_label           str          Short label, e.g. "NVDA"           ← set by step 2
tickers               list[str]    Stock/index symbols                ← set by step 2
support_levels        list[float]  Support price levels               ← set by step 2, refined by step 7
resistance_levels     list[float]  Resistance price levels            ← set by step 2, refined by step 7

summary               str          Narration text                     ← set by step 3
translated_summary    str          Translated narration               ← set by step 4

audio_path            str          Path to narration MP3              ← set by step 5
frame_paths           list[str]    Extracted video frames             ← set by step 6
slide_paths           list[str]    Generated info slides              ← set by step 7
chart_paths           list[str]    Generated candlestick charts       ← set by step 7
```

### Models in Use

| Category | CLI flag | Default | Used by |
|----------|----------|---------|---------|
| Text / Vision | `--textmodel` | `gpt-5-mini` | Segmentation, summarization, translation, slides, GPT Vision (S/R) |
| Speech | `--speechmodel` | `tts-1-hd` | OpenAI TTS narration |
| Transcription | `--transcriptmodel` | `whisper-1` | Audio transcription fallback |
| ElevenLabs | `--elevenlabs-model` | `eleven_multilingual_v2` | Voice cloning narration |
