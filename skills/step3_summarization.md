# Step 3: Summarization

## Purpose
Summarize each segment's transcript into narration-ready text, respecting the target compression ratio.

## Current Behavior
- If `--length` is set, calculates compression ratio = target_length / video_duration
- Makes one GPT call per segment
- Generates flowing narration text (not bullet points)
- If no `--length` is specified, copies the full transcript as-is (no summarization)

## LLM Usage
- **Model**: `text_model` (default `gpt-5-mini`)
- **Temperature**: 0.3
- **Calls**: 1 per segment
- **System prompt**: Video content summarizer. Writes narration for voice-over. Natural, engaging tone. No bullet points or markdown. Includes compression instruction based on ratio.
- **User prompt**: Segment index, time range, and full transcript text.

## Compression Levels (auto-calculated from ratio)
| Ratio     | Instruction                                      |
|-----------|--------------------------------------------------|
| >= 1.0    | Keep full content, preserve all details           |
| >= 0.7    | Detailed summary, ~70% of original               |
| >= 0.45   | Moderate summary, main points + important details |
| >= 0.25   | Concise summary, key points only                  |
| >= 0.10   | Very brief, essential takeaways only              |
| < 0.10    | Ultra-brief, 1-2 sentences                        |

## Input
- `step2_segmentation/segments.json` — segments with text
- `step1_download/video_info.json` — duration (for ratio calculation)

## Output
Saved to `stepN_summarization/`:
- `segments.json` — segments with `summary` field populated

## Instructions
<!-- Customize this section to control summarization behavior -->
<!-- Examples: tone of narration, what details to prioritize, -->
<!-- how to handle numbers/data, preferred sentence structure -->
