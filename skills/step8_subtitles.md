# Step 8: Subtitle Generation

## Purpose
Generate SRT and VTT subtitle files from the translated summaries for YouTube closed captions upload.

## Current Behavior
- Splits translated text into subtitle-sized chunks (max 84 chars = ~2 lines x 42 chars)
- Tries sentence boundaries first, then word boundaries
- Distributes chunks evenly across segment time range
- Generates both SRT and VTT formats by default
- Skipped entirely if `generate_subtitles` is false

## LLM Usage
- **No LLM call** — pure text processing

## Input
- `step7_visuals/segments.json` — segments with `translated_summary` or `summary`
- `step1_download/video_info.json` — title (for output filename)

## Output
Saved to `stepN_subtitles/`:
- `segments.json` — segments (unchanged, passed through)
- `{title}_{lang}.srt` — SRT format subtitle file
- `{title}_{lang}.vtt` — WebVTT format subtitle file

## Subtitle Formatting
- SRT timestamp format: `HH:MM:SS,mmm --> HH:MM:SS,mmm`
- VTT timestamp format: `HH:MM:SS.mmm --> HH:MM:SS.mmm`
- YouTube recommendation: max 2 lines, 42 chars per line

## Instructions
<!-- Customize this section to control subtitle generation -->
<!-- Examples: max chars per line, subtitle display duration, -->
<!-- whether to include timing adjustments for readability -->
