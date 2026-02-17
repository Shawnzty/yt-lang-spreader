"""Generate speech audio from text using multiple TTS backends.

Supported backends:
  - "gtts"        : Free Google TTS (robotic but free)
  - "elevenlabs"  : ElevenLabs API — supports voice cloning from your own voice
  - "openai_tts"  : OpenAI TTS API
  - "local"       : Use pre-recorded audio files from a directory (your own voice)
"""

from __future__ import annotations

import os
import shutil

from ..core.config import PipelineConfig
from ..core.models import Segment

# gTTS language code mapping
GTTS_LANG_MAP = {
    "zh": "zh-CN",
    "zh-TW": "zh-TW",
    "en": "en",
    "es": "es",
    "fr": "fr",
    "de": "de",
    "ja": "ja",
    "ko": "ko",
    "pt": "pt",
    "ru": "ru",
    "ar": "ar",
    "hi": "hi",
    "it": "it",
    "nl": "nl",
    "pl": "pl",
    "tr": "tr",
    "vi": "vi",
    "th": "th",
    "sv": "sv",
}


def generate_narration(
    segments: list[Segment],
    config: PipelineConfig,
    output_dir: str,
) -> list[Segment]:
    """Generate speech audio files for each segment.

    Dispatches to the backend specified in config.tts_backend.
    Updates each segment's audio_path in-place.

    Returns the updated segments.
    """
    os.makedirs(output_dir, exist_ok=True)

    backend = config.tts_backend.lower()
    if backend == "gtts":
        _generate_gtts(segments, config, output_dir)
    elif backend == "elevenlabs":
        _generate_elevenlabs(segments, config, output_dir)
    elif backend == "openai_tts":
        _generate_openai_tts(segments, config, output_dir)
    elif backend == "local":
        _load_local_recordings(segments, config, output_dir)
    else:
        raise ValueError(
            f"Unknown TTS backend '{backend}'. "
            "Choose from: gtts, elevenlabs, openai_tts, local"
        )

    return segments


# ---------------------------------------------------------------------------
# Backend: Google TTS (free, no API key)
# ---------------------------------------------------------------------------

def _generate_gtts(
    segments: list[Segment], config: PipelineConfig, output_dir: str
) -> None:
    from gtts import gTTS

    gtts_lang = GTTS_LANG_MAP.get(config.target_lang, config.target_lang)

    for segment in segments:
        text = segment.translated_summary or segment.summary
        if not text:
            continue

        audio_path = os.path.join(output_dir, f"narration_{segment.index:03d}.mp3")
        tts = gTTS(text=text, lang=gtts_lang, slow=False)
        tts.save(audio_path)
        segment.audio_path = audio_path


# ---------------------------------------------------------------------------
# Backend: ElevenLabs (voice cloning — use YOUR voice)
# ---------------------------------------------------------------------------

def _generate_elevenlabs(
    segments: list[Segment], config: PipelineConfig, output_dir: str
) -> None:
    """Generate narration using ElevenLabs API.

    To use your own cloned voice:
      1. Go to https://elevenlabs.io  →  Voice Lab  →  "Add Generative or Cloned Voice"
      2. Upload samples of your voice and create the voice clone.
      3. Copy the Voice ID from the voice settings page.
      4. Pass it via --elevenlabs-voice-id or config.elevenlabs_voice_id.

    Set ELEVENLABS_API_KEY env var or pass --elevenlabs-api-key.
    """
    import requests

    api_key = config.elevenlabs_api_key
    if not api_key:
        raise ValueError(
            "ElevenLabs API key required. Set ELEVENLABS_API_KEY env var "
            "or pass --elevenlabs-api-key."
        )

    voice_id = config.elevenlabs_voice_id
    if not voice_id:
        raise ValueError(
            "ElevenLabs voice ID required. Clone your voice at "
            "https://elevenlabs.io/voice-lab and pass --elevenlabs-voice-id."
        )

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }

    for segment in segments:
        text = segment.translated_summary or segment.summary
        if not text:
            continue

        audio_path = os.path.join(output_dir, f"narration_{segment.index:03d}.mp3")

        payload = {
            "text": text,
            "model_id": config.elevenlabs_model,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()

        with open(audio_path, "wb") as f:
            f.write(resp.content)

        segment.audio_path = audio_path


# ---------------------------------------------------------------------------
# Backend: OpenAI TTS
# ---------------------------------------------------------------------------

def _generate_openai_tts(
    segments: list[Segment], config: PipelineConfig, output_dir: str
) -> None:
    """Generate narration using OpenAI TTS API."""
    from openai import OpenAI

    client = OpenAI(api_key=config.openai_api_key)

    for segment in segments:
        text = segment.translated_summary or segment.summary
        if not text:
            continue

        audio_path = os.path.join(output_dir, f"narration_{segment.index:03d}.mp3")

        response = client.audio.speech.create(
            model=config.speech_model,
            voice=config.openai_tts_voice,
            input=text,
        )
        response.stream_to_file(audio_path)
        segment.audio_path = audio_path


# ---------------------------------------------------------------------------
# Backend: Local pre-recorded audio (YOUR own voice recordings)
# ---------------------------------------------------------------------------

def _load_local_recordings(
    segments: list[Segment], config: PipelineConfig, output_dir: str
) -> None:
    """Load pre-recorded audio files from a directory.

    Expected file naming convention in config.local_voice_dir:
      narration_001.mp3  (or .wav, .m4a, .ogg)
      narration_002.mp3
      ...

    The number corresponds to the segment index.
    This lets you record narration in your own voice and use it directly.
    """
    voice_dir = config.local_voice_dir
    if not voice_dir or not os.path.isdir(voice_dir):
        raise ValueError(
            f"Local voice directory not found: '{voice_dir}'. "
            "Create a directory with audio files named narration_001.mp3, "
            "narration_002.mp3, etc."
        )

    for segment in segments:
        found = False
        for ext in ("mp3", "wav", "m4a", "ogg"):
            src = os.path.join(voice_dir, f"narration_{segment.index:03d}.{ext}")
            if os.path.exists(src):
                dst = os.path.join(output_dir, f"narration_{segment.index:03d}.{ext}")
                shutil.copy2(src, dst)
                segment.audio_path = dst
                found = True
                break

        if not found:
            print(
                f"  Warning: No audio file found for segment {segment.index} "
                f"in {voice_dir}. Skipping."
            )
