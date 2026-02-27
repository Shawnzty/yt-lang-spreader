# Step 9: Video Assembly

## Purpose
Assemble the final video by combining visual assets with narration audio and optional subtitle overlays.

## Current Behavior

### Visual Routing by Topic Type
| topic_type    | Primary visuals   | Fallback          |
|---------------|-------------------|--------------------|
| macro         | slide_paths       | frame_paths        |
| index / stock | chart_paths       | frame_paths        |
| other         | all available      | text-only clip     |

### Assembly Process
1. For each segment with audio, select images based on topic type
2. Create slideshow: distribute images evenly across audio duration
3. Optionally overlay subtitle text at bottom of frame
4. If no images available, create a text-only clip (dark background + centered text)
5. Concatenate all segment clips into final video

### Encoding
- Codec: H.264 (libx264)
- Audio: AAC
- FPS: 24
- Resolution: configurable (default 1280x720)

## LLM Usage
- **No LLM call** — pure video processing with moviepy

## Input
- `step8_subtitles/segments.json` — segments with audio_path, frame_paths, slide_paths, chart_paths, translated_summary
- `step1_download/video_info.json` — title (for output filename)

## Output
Saved to `stepN_video/`:
- `{title}_{lang}.mp4` — final assembled video
- `{title}_{lang}_metadata.json` — full metadata (source URL, models used, segment details)

## Instructions
<!-- Customize this section to control video assembly -->
<!-- Examples: transition effects between segments, subtitle position/style, -->
<!-- intro/outro slides, background music, resolution preferences -->
