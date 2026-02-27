# Step 6: Key Frame Extraction

## Purpose
Extract still frames from the original video at evenly distributed points within each segment's time range.

## Current Behavior
- Uses ffmpeg to extract frames at calculated timestamps
- Distributes frames evenly across each segment's duration
- Saves frames as JPEG images
- Default: 3 frames per segment

## LLM Usage
- **No LLM call** — pure ffmpeg operation

## Input
- `step5_narration/segments.json` — segments with time boundaries
- `step1_download/video_info.json` — video_path to the original MP4

## Output
Saved to `stepN_keyframes/`:
- `segments.json` — segments with `frame_paths` list populated
- `frame_001_00.jpg`, `frame_001_01.jpg`, `frame_001_02.jpg`, ... — extracted frames

## Frame Selection
For a segment from 60s to 180s with 3 frames:
- interval = 120 / (3+1) = 30s
- Frame 1: 90s, Frame 2: 120s, Frame 3: 150s

## Instructions
<!-- Customize this section to control frame extraction behavior -->
<!-- Examples: number of frames per segment, quality settings, -->
<!-- whether to prefer frames at specific moments (chart close-ups, etc.) -->
