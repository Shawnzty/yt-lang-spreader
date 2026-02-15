"""Generate speech audio from translated text using gTTS."""

import os

from gtts import gTTS

from .segmenter import Segment

# gTTS language code mapping (gTTS uses slightly different codes)
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
    target_lang: str,
    output_dir: str,
) -> list[str]:
    """Generate speech audio files for each translated segment.

    Args:
        segments: List of Segment objects with translated_summary filled in.
        target_lang: Language code for TTS.
        output_dir: Directory to save audio files.

    Returns:
        List of paths to generated audio files, one per segment.
    """
    os.makedirs(output_dir, exist_ok=True)
    gtts_lang = GTTS_LANG_MAP.get(target_lang, target_lang)

    audio_paths = []
    for segment in segments:
        audio_path = os.path.join(output_dir, f"narration_{segment.index:03d}.mp3")

        text = segment.translated_summary or segment.summary
        if not text:
            # Create a short silence placeholder
            audio_paths.append("")
            continue

        tts = gTTS(text=text, lang=gtts_lang, slow=False)
        tts.save(audio_path)
        audio_paths.append(audio_path)

    return audio_paths
