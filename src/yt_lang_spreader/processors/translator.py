"""Translate summarized segments using OpenAI GPT."""

from __future__ import annotations

from openai import OpenAI

from ..core.models import Segment
from ..utils.openai_compat import chat_completion_params

LANGUAGE_NAMES = {
    "zh": "Simplified Chinese",
    "zh-TW": "Traditional Chinese",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "ja": "Japanese",
    "ko": "Korean",
    "pt": "Portuguese",
    "ru": "Russian",
    "ar": "Arabic",
    "hi": "Hindi",
    "it": "Italian",
    "nl": "Dutch",
    "pl": "Polish",
    "tr": "Turkish",
    "vi": "Vietnamese",
    "th": "Thai",
    "sv": "Swedish",
    "en": "English",
}


def translate_segments(
    segments: list[Segment],
    target_lang: str,
    api_key: str = "",
    model: str = "gpt-5-mini",
) -> list[Segment]:
    """Translate the summary of each segment to the target language."""
    lang_name = LANGUAGE_NAMES.get(target_lang, target_lang)
    client = OpenAI(api_key=api_key)

    system_prompt = (
        f"You are a professional translator. Translate the following narration "
        f"text to {lang_name}. Maintain the natural, spoken tone suitable for "
        f"voice-over narration. Do not add any explanations or notes. "
        f"Only output the translated text."
    )

    for segment in segments:
        if not segment.summary:
            segment.translated_summary = ""
            continue

        response = client.chat.completions.create(
            **chat_completion_params(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": segment.summary},
                ],
                temperature=0.3,
            )
        )
        segment.translated_summary = response.choices[0].message.content.strip()

    return segments
