"""Segment subtitles by semantic topic using GPT.

Finance video structure detected:
  1. "macro"  — general market info, breaking news, Fed meetings, macro economics
  2. "index"  — market indices (S&P 500, NASDAQ, Philadelphia Semiconductor, etc.)
  3. "stock"  — individual stock analysis (AAPL, NVDA, TSLA, etc.)

GPT reads the full timestamped transcript and returns topic boundaries,
classified types, tickers, and mentioned support/resistance levels.
"""

from __future__ import annotations

import json
import re

from openai import OpenAI

from ..core.models import Segment
from ..utils.openai_compat import chat_completion_params


_SEGMENTATION_SYSTEM_PROMPT = """\
You are a financial video transcript analyst. You will receive a timestamped \
transcript from a YouTube finance video. Your job is to split it into semantic \
segments based on the TOPIC being discussed.

Typical structure (in order, but some may be absent):
  1. "macro" — general market news, breaking news, Fed meetings, interest rates, \
macro economics, geopolitics, earnings season overview.
  2. "index" — discussion of market indices like S&P 500 (SPX/SPY), NASDAQ (QQQ), \
Philadelphia Semiconductor Index (SOX/SOXX), Dow Jones (DJI), Russell 2000 (IWM), etc.
  3. "stock" — analysis of individual stocks (e.g. NVDA, AAPL, TSLA, AMZN, META).

For each segment output:
- "start": the timestamp (in seconds) where this topic begins
- "end": the timestamp (in seconds) where this topic ends
- "topic_type": one of "macro", "index", "stock"
- "topic_label": a short label, e.g. "Fed Rate Decision", "S&P 500", "NVDA"
- "tickers": list of stock/index tickers mentioned (use standard symbols like \
SPY, QQQ, SOXX, NVDA, AAPL, etc.). For indices use the ETF ticker.
- "support_levels": list of numeric support prices mentioned for the main ticker
- "resistance_levels": list of numeric resistance prices mentioned for the main ticker

IMPORTANT rules:
- If the video discusses one stock then switches to another, those are SEPARATE segments.
- Merge consecutive subtitles about the SAME topic into ONE segment.
- A segment discussing SP500 is "index", not "stock".
- Return valid JSON array. No markdown fences.
- Timestamps must be in seconds (float), matching the input timestamps.
"""

_SEGMENTATION_USER_TEMPLATE = """\
Video title: {title}

Timestamped transcript:
{transcript}

Return a JSON array of segments. Each element:
{{"start": <float>, "end": <float>, "topic_type": "<macro|index|stock>", \
"topic_label": "<short label>", "tickers": ["SYM", ...], \
"support_levels": [<float>, ...], "resistance_levels": [<float>, ...]}}
"""


def segment_subtitles(
    subtitles: list[dict],
    duration: float,
    num_segments: int | None = None,
    segment_duration: float = 120.0,
    api_key: str = "",
    model: str = "gpt-5-mini",
    video_title: str = "",
) -> list[Segment]:
    """Segment subtitles by semantic topic using GPT.

    Falls back to time-based segmentation if GPT is unavailable or fails.
    """
    if api_key:
        try:
            return _segment_semantic(
                subtitles, duration, api_key, model, video_title
            )
        except Exception as e:
            print(f"      Semantic segmentation failed ({e}), falling back to time-based")

    return _segment_time_based(subtitles, duration, num_segments, segment_duration)


def _segment_semantic(
    subtitles: list[dict],
    duration: float,
    api_key: str,
    model: str,
    video_title: str,
) -> list[Segment]:
    """Use GPT to identify topic boundaries in the transcript."""
    transcript_lines = []
    for sub in subtitles:
        t = f"[{sub['start']:.1f}s] {sub['text']}"
        transcript_lines.append(t)
    transcript_text = "\n".join(transcript_lines)

    # Truncate if extremely long (GPT context limit safety)
    if len(transcript_text) > 80_000:
        transcript_text = transcript_text[:80_000] + "\n[... truncated]"

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        **chat_completion_params(
            model=model,
            messages=[
                {"role": "system", "content": _SEGMENTATION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _SEGMENTATION_USER_TEMPLATE.format(
                        title=video_title,
                        transcript=transcript_text,
                    ),
                },
            ],
            temperature=0.1,
        )
    )

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    seg_data = json.loads(raw)
    if not isinstance(seg_data, list) or not seg_data:
        raise ValueError("GPT returned empty or non-list response")

    segments: list[Segment] = []
    for idx, item in enumerate(seg_data):
        start = float(item.get("start", 0))
        end = float(item.get("end", duration))
        start = max(0, min(start, duration))
        end = max(start + 0.1, min(end, duration))

        # Collect subtitle text in this time range
        texts = []
        for sub in subtitles:
            if sub["end"] > start and sub["start"] < end:
                texts.append(sub["text"])
        combined_text = " ".join(texts).strip() or "(No narration in this segment)"

        support = [float(v) for v in item.get("support_levels", []) if _is_number(v)]
        resistance = [float(v) for v in item.get("resistance_levels", []) if _is_number(v)]

        segments.append(Segment(
            index=idx + 1,
            start=start,
            end=end,
            text=combined_text,
            topic_type=item.get("topic_type", "macro"),
            topic_label=item.get("topic_label", ""),
            tickers=item.get("tickers", []),
            support_levels=support,
            resistance_levels=resistance,
        ))

    return segments


def _segment_time_based(
    subtitles: list[dict],
    duration: float,
    num_segments: int | None,
    segment_duration: float,
) -> list[Segment]:
    """Fallback: split by even time intervals."""
    if not subtitles:
        raise ValueError("No subtitles to segment.")

    if num_segments is None:
        num_segments = max(1, round(duration / segment_duration))

    seg_len = duration / num_segments
    segments: list[Segment] = []

    for idx in range(num_segments):
        seg_start = idx * seg_len
        seg_end = (idx + 1) * seg_len
        texts = [
            sub["text"] for sub in subtitles
            if sub["end"] > seg_start and sub["start"] < seg_end
        ]
        combined = " ".join(texts).strip() or "(No narration in this segment)"
        segments.append(Segment(
            index=idx + 1,
            start=seg_start,
            end=seg_end,
            text=combined,
            topic_type="macro",
        ))

    return segments


def _is_number(v) -> bool:
    try:
        float(v)
        return True
    except (ValueError, TypeError):
        return False
