"""Summarize video segments using OpenAI GPT."""

from __future__ import annotations

from openai import OpenAI

from ..core.models import Segment
from ..utils.formatting import format_time_short

COMPRESSION_PROMPTS = {
    1: (
        "Provide a detailed summary that retains most of the original content. "
        "Keep key details, examples, and explanations. "
        "Target length: about 70-80% of the original."
    ),
    2: (
        "Provide a moderate summary that captures the main points and important details. "
        "Remove redundancy but keep the narrative flow. "
        "Target length: about 50-60% of the original."
    ),
    3: (
        "Provide a concise summary of the key points only. "
        "Focus on the main ideas and conclusions. "
        "Target length: about 30-40% of the original."
    ),
    4: (
        "Provide a very brief summary with only the essential takeaways. "
        "Use short, direct sentences. "
        "Target length: about 15-25% of the original."
    ),
    5: (
        "Provide an ultra-brief summary in 1-2 sentences. "
        "Only the single most important point. "
        "Target length: about 5-10% of the original."
    ),
}


def summarize_segments(
    segments: list[Segment],
    video_title: str,
    compression_level: int = 3,
    api_key: str = "",
    model: str = "gpt-4o-mini",
) -> list[Segment]:
    """Summarize each segment using OpenAI."""
    compression_level = max(1, min(5, compression_level))
    compression_prompt = COMPRESSION_PROMPTS[compression_level]

    client = OpenAI(api_key=api_key)

    system_prompt = (
        "You are a video content summarizer. You will receive a transcript segment "
        "from a YouTube video. Summarize it as narration that could be spoken over "
        "key frames of the video. Write in a natural, engaging tone suitable for "
        "voice narration. Do not use bullet points or markdown formatting. "
        "Write flowing paragraphs.\n\n"
        f"Video title: {video_title}\n\n"
        f"Compression instruction: {compression_prompt}"
    )

    for segment in segments:
        if segment.text == "(No narration in this segment)":
            segment.summary = ""
            continue

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Segment {segment.index} "
                        f"({format_time_short(segment.start)} - "
                        f"{format_time_short(segment.end)}):\n\n"
                        f"{segment.text}"
                    ),
                },
            ],
            temperature=0.3,
        )
        segment.summary = response.choices[0].message.content.strip()

    return segments
