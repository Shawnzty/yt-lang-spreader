# Step 4: Translation

## Purpose
Translate each segment's summary into the target language, maintaining a natural spoken tone suitable for voice narration.

## Current Behavior
- Makes one GPT call per segment
- Translates summary text to the target language
- Preserves natural, spoken tone for voice-over
- Skips segments with empty summaries

## LLM Usage
- **Model**: `text_model` (default `gpt-5-mini`)
- **Temperature**: 0.3
- **Calls**: 1 per segment
- **System prompt**: Professional translator. Translates to target language name. Maintains spoken tone for voice-over narration. No explanations or notes.
- **User prompt**: The segment summary text (nothing else).

## Supported Languages
zh (Simplified Chinese), zh-TW (Traditional Chinese), en, es, fr, de, ja, ko, pt, ru, ar, hi, it, nl, pl, tr, vi, th, sv

## Input
- `step3_summarization/segments.json` — segments with `summary` field

## Output
Saved to `stepN_translation/`:
- `segments.json` — segments with `translated_summary` field populated

## Instructions
<!-- Customize this section to control translation behavior -->
<!-- Examples: preferred terminology, formal vs casual tone, -->
<!-- how to handle financial jargon, specific term translations -->
