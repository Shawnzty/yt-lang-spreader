# Step 1: Download & Transcript Extraction

## Purpose
Download the YouTube video and extract its transcript (subtitles or audio transcription).

## Current Behavior
- Downloads video via `yt-dlp` in MP4 format
- Tries to extract subtitles: manual subs → auto-generated subs, across json3 → srv3 → vtt formats
- Falls back to OpenAI Whisper audio transcription if no subtitles are available
- Detects source language automatically or uses the user-specified `--source-lang`

## LLM Usage
- **Model**: Whisper (`transcript_model`, default `whisper-1`)
- **When**: Only when YouTube subtitles are unavailable (fallback)
- **What**: Splits audio into 10-minute chunks, sends each to Whisper for speech-to-text

## Input
- YouTube URL
- Source language (auto-detect or specified)

## Output
Saved to `stepN_download/`:
- `video_info.json` — video_id, title, duration, video_path, subtitles list, transcript_source, transcript_language
- Downloaded `.mp4` video file
- Subtitle files (if extracted from YouTube)

## Instructions
<!-- Customize this section to control how this step behaves -->
<!-- Examples: preferred subtitle language, transcription quality, etc. -->
