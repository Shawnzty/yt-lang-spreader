"""Summarize video segments using OpenAI GPT."""

from __future__ import annotations

from openai import OpenAI

from ..core.models import Segment
from ..utils.formatting import format_time_short
from ..utils.openai_compat import chat_completion_params
from ..utils.skills import load_skill_instructions


def _build_compression_instruction(ratio: float) -> str:
    """Build a GPT instruction string based on the target compression ratio.

    Args:
        ratio: target_length / original_length  (0.0–1.0).
               Values >=1.0 mean no compression needed.
    """
    pct = int(round(ratio * 100))
    if ratio >= 1.0:
        return (
            "No compression is needed. Keep the full content, preserving all details, "
            "examples, and explanations. Rewrite as smooth narration."
        )
    if ratio >= 0.7:
        return (
            f"Provide a detailed summary that retains most of the original content. "
            f"Keep key details, examples, and explanations. "
            f"Target length: about {pct}% of the original."
        )
    if ratio >= 0.45:
        return (
            f"Provide a moderate summary that captures the main points and important details. "
            f"Remove redundancy but keep the narrative flow. "
            f"Target length: about {pct}% of the original."
        )
    if ratio >= 0.25:
        return (
            f"Provide a concise summary of the key points only. "
            f"Focus on the main ideas and conclusions. "
            f"Target length: about {pct}% of the original."
        )
    if ratio >= 0.10:
        return (
            f"Provide a very brief summary with only the essential takeaways. "
            f"Use short, direct sentences. "
            f"Target length: about {pct}% of the original."
        )
    return (
        f"Provide an ultra-brief summary in 1-2 sentences. "
        f"Only the single most important point. "
        f"Target length: about {pct}% of the original."
    )


def summarize_segments(
    segments: list[Segment],
    video_title: str,
    compression_ratio: float = 1.0,
    api_key: str = "",
    model: str = "gpt-5-mini",
) -> list[Segment]:
    """Summarize each segment using OpenAI.

    Args:
        segments: list of Segment objects with .text populated.
        video_title: title of the video (for GPT context).
        compression_ratio: target_length / original_length (0.0–1.0).
            1.0 means no compression; 0.5 means ~50% of original, etc.
        api_key: OpenAI API key.
        model: OpenAI model name.
    """
    compression_instruction = _build_compression_instruction(compression_ratio)

    client = OpenAI(api_key=api_key)

    system_prompt = (
        "You are a video content summarizer. You will receive a transcript segment "
        "from a YouTube video. Summarize it as narration that could be spoken over "
        "key frames of the video. Write in a natural, engaging tone suitable for "
        "voice narration. Do not use bullet points or markdown formatting. "
        "Write flowing paragraphs.\n\n"
        f"Video title: {video_title}\n\n"
        f"Compression instruction: {compression_instruction}"
    )
    extra = load_skill_instructions(3)
    if extra:
        system_prompt += "\n\nAdditional instructions:\n" + extra

    for segment in segments:
        if segment.text == "(No narration in this segment)":
            segment.summary = ""
            continue

        response = client.chat.completions.create(
            **chat_completion_params(
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
        )
        segment.summary = response.choices[0].message.content.strip()

    return segments
