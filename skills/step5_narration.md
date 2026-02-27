# Step 5: Narration (TTS)

## Purpose
Generate speech audio files from the translated (or original) text using a TTS backend.

## Current Behavior
- Reads `translated_summary` for each segment (falls back to `summary`)
- Dispatches to the configured TTS backend
- Saves one MP3 file per segment

## LLM Usage
- **No LLM call** — uses TTS APIs only
- **Speech model**: `speech_model` (default `tts-1-hd` for OpenAI TTS)
- **ElevenLabs model**: `elevenlabs_model` (default `eleven_multilingual_v2`)

## TTS Backends
| Backend       | Description                          | Config needed                                      |
|---------------|--------------------------------------|----------------------------------------------------|
| `gtts`        | Free Google TTS (robotic)            | None                                               |
| `elevenlabs`  | ElevenLabs voice cloning (your voice)| `--elevenlabs-api-key`, `--elevenlabs-voice-id`    |
| `openai_tts`  | OpenAI TTS API                       | `--speechmodel`, `--openai-tts-voice`              |
| `local`       | Pre-recorded audio files             | `--local-voice-dir` with narration_001.mp3, etc.   |

## Input
- `step4_translation/segments.json` — segments with `translated_summary`

## Output
Saved to `stepN_narration/`:
- `segments.json` — segments with `audio_path` field populated
- `narration_001.mp3`, `narration_002.mp3`, ... — audio files per segment

## Instructions
<!-- Customize this section to control narration behavior -->
<!-- Examples: preferred voice, speaking speed, pronunciation notes -->
