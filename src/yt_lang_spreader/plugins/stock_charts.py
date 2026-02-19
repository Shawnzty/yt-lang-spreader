"""Stock chart plotting plugin.

Generates candlestick charts with support/resistance annotations.
Supports two data backends:
  - Longport API (default) — for HK/US/CN markets
  - yfinance (fallback)    — free Yahoo Finance data

Support/resistance levels come from:
  1. The semantic segmenter (parsed from transcript via GPT)
  2. GPT-4 Vision analysis of screenshots from the original video
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from datetime import datetime, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ..core.config import PipelineConfig
from ..core.models import Segment
from ..utils.openai_compat import chat_completion_params


def generate_stock_charts(
    segments: list[Segment],
    output_dir: str,
    config: PipelineConfig,
    period_days: int = 180,
) -> list[Segment]:
    """Generate candlestick charts for index/stock segments.

    For each segment with topic_type "index" or "stock":
    1. Use GPT Vision on extracted key frames to refine S/R levels
    2. Fetch OHLCV data via Longport (default) or yfinance
    3. Plot candlestick chart with S/R annotations

    Updates segment.chart_paths in-place.
    """
    os.makedirs(output_dir, exist_ok=True)

    for segment in segments:
        if segment.topic_type not in ("index", "stock"):
            continue
        if not segment.tickers:
            continue

        # Step 1: Refine S/R from screenshots via GPT Vision
        if segment.frame_paths and config.openai_api_key:
            _refine_levels_from_frames(segment, config)

        # Step 2: Generate chart for each ticker
        for ticker in segment.tickers:
            chart_path = os.path.join(
                output_dir, f"chart_{segment.index:03d}_{ticker}.png"
            )
            try:
                ohlcv = _fetch_ohlcv(ticker, period_days, config)
                if not ohlcv:
                    should_skip = _prompt_skip_missing_ticker(ticker)
                    if should_skip:
                        print(f"      No data for {ticker}, skipping chart")
                        continue
                    print("Software is terminated.")
                    raise SystemExit(1)
                _plot_candlestick(
                    ticker=ticker,
                    ohlcv=ohlcv,
                    support_levels=segment.support_levels,
                    resistance_levels=segment.resistance_levels,
                    output_path=chart_path,
                )
                segment.chart_paths.append(chart_path)
            except Exception as e:
                print(f"      Warning: chart for {ticker} failed: {e}")

    return segments


# ---------------------------------------------------------------------------
# GPT Vision: extract S/R from original video screenshots
# ---------------------------------------------------------------------------

def _refine_levels_from_frames(segment: Segment, config: PipelineConfig) -> None:
    """Use GPT-4 Vision to read S/R levels from the original video frames."""
    from openai import OpenAI

    frames_to_analyze = segment.frame_paths[:3]
    if not frames_to_analyze:
        return

    image_contents = []
    for fp in frames_to_analyze:
        try:
            with open(fp, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            image_contents.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            })
        except Exception:
            continue

    if not image_contents:
        return

    client = OpenAI(api_key=config.openai_api_key)

    prompt = (
        f"These are screenshots from a finance video about {', '.join(segment.tickers)}. "
        "Look at the charts shown in the screenshots. "
        "Extract any support levels and resistance levels you can see "
        "(horizontal lines, annotations, or price levels marked on the chart). "
        "Return ONLY a JSON object like: "
        '{"support": [123.45, 130.0], "resistance": [150.0, 160.5]}. '
        "If you can't find any, return empty lists. No explanation."
    )

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                *image_contents,
            ],
        }
    ]

    try:
        response = client.chat.completions.create(
            **chat_completion_params(
                model=config.text_model,
                messages=messages,
                max_tokens=200,
                temperature=0,
            )
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        data = json.loads(raw)
        vision_support = [float(v) for v in data.get("support", []) if _is_number(v)]
        vision_resist = [float(v) for v in data.get("resistance", []) if _is_number(v)]

        segment.support_levels = _merge_levels(segment.support_levels, vision_support)
        segment.resistance_levels = _merge_levels(segment.resistance_levels, vision_resist)
    except Exception as e:
        print(f"      Vision S/R extraction failed for segment {segment.index}: {e}")


def _merge_levels(existing: list[float], new: list[float], tolerance: float = 0.02) -> list[float]:
    """Merge two level lists, deduplicating values within tolerance (%)."""
    merged = list(existing)
    for val in new:
        is_dup = False
        for ex in merged:
            if ex != 0 and abs(val - ex) / abs(ex) < tolerance:
                is_dup = True
                break
        if not is_dup:
            merged.append(val)
    return sorted(merged)


# ---------------------------------------------------------------------------
# Data fetching: Longport (default) / yfinance (fallback)
# ---------------------------------------------------------------------------

def _fetch_ohlcv(
    ticker: str, period_days: int, config: PipelineConfig
) -> list[dict]:
    """Fetch OHLCV data. Returns list of dicts with date/open/high/low/close/volume."""
    if config.stock_api == "longport" and config.longport_app_key:
        try:
            return _fetch_longport(ticker, period_days, config)
        except Exception as e:
            print(f"      Longport failed for {ticker}: {e}, trying yfinance")

    return _fetch_yfinance(ticker, period_days)


def _fetch_longport(
    ticker: str, period_days: int, config: PipelineConfig
) -> list[dict]:
    """Fetch candlestick data from Longport OpenAPI."""
    from longport.openapi import QuoteContext, Config, Period, AdjustType

    lp_config = Config(
        app_key=config.longport_app_key,
        app_secret=config.longport_app_secret,
        access_token=config.longport_access_token,
    )
    ctx = QuoteContext(lp_config)
    symbol = _to_longport_symbol(ticker)

    resp = ctx.candlesticks(
        symbol,
        Period.Day,
        count=period_days,
        adjust_type=AdjustType.ForwardAdjust,
    )

    ohlcv = []
    for c in resp:
        date_str = (
            c.timestamp.strftime("%Y-%m-%d")
            if hasattr(c.timestamp, "strftime")
            else str(c.timestamp)[:10]
        )
        ohlcv.append({
            "date": date_str,
            "open": float(c.open),
            "high": float(c.high),
            "low": float(c.low),
            "close": float(c.close),
            "volume": int(c.volume),
        })
    return ohlcv


def _to_longport_symbol(ticker: str) -> str:
    """Convert a simple ticker to Longport symbol format (AAPL -> AAPL.US)."""
    ticker = ticker.upper().strip()
    if "." in ticker:
        return ticker
    return f"{ticker}.US"


def _fetch_yfinance(ticker: str, period_days: int) -> list[dict]:
    """Fetch OHLCV data from Yahoo Finance (fallback)."""
    try:
        import yfinance as yf
    except ImportError:
        print("      yfinance not installed. Run: pip install yfinance")
        return []

    period_map = {30: "1mo", 60: "2mo", 90: "3mo", 180: "6mo", 365: "1y"}
    period = "6mo"
    for days, pstr in sorted(period_map.items()):
        if period_days <= days:
            period = pstr
            break

    data = None
    for symbol in _yfinance_candidates(ticker):
        data = yf.download(symbol, period=period, progress=False)
        if not data.empty:
            break

    if data is None or data.empty:
        return []

    if hasattr(data.columns, "levels") and len(data.columns.levels) > 1:
        data.columns = data.columns.get_level_values(0)

    ohlcv = []
    for idx, row in data.iterrows():
        ohlcv.append({
            "date": idx.strftime("%Y-%m-%d"),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"]),
        })
    return ohlcv


def _yfinance_candidates(ticker: str) -> list[str]:
    """Generate likely Yahoo symbols for a ticker/index alias."""
    normalized = ticker.strip().upper().lstrip("$")
    if not normalized:
        return []

    aliases = {
        "VIX": "^VIX",
        "SPX": "^GSPC",
        "SP500": "^GSPC",
        "DJI": "^DJI",
        "DJIA": "^DJI",
        "NASDAQ": "^IXIC",
        "NDX": "^NDX",
        "RUT": "^RUT",
    }

    mapped = aliases.get(normalized)
    candidates = []
    if mapped:
        candidates.append(mapped)
    if normalized not in candidates:
        candidates.append(normalized)
    return candidates


def _prompt_skip_missing_ticker(ticker: str) -> bool:
    """Ask user whether to skip a ticker when both providers return no data."""
    prompt = (
        f"No data found for ticker '{ticker}' from Longport and yfinance. "
        "Skip this part and continue? [y/N]: "
    )
    if not sys.stdin or not sys.stdin.isatty():
        return False
    try:
        answer = input(prompt).strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}


# ---------------------------------------------------------------------------
# Candlestick chart plotting
# ---------------------------------------------------------------------------

def _plot_candlestick(
    ticker: str,
    ohlcv: list[dict],
    support_levels: list[float],
    resistance_levels: list[float],
    output_path: str,
) -> None:
    """Plot a candlestick chart with S/R annotations and moving averages."""
    dates = [datetime.strptime(d["date"], "%Y-%m-%d") for d in ohlcv]
    opens = [d["open"] for d in ohlcv]
    highs = [d["high"] for d in ohlcv]
    lows = [d["low"] for d in ohlcv]
    closes = [d["close"] for d in ohlcv]
    volumes = [d["volume"] for d in ohlcv]

    fig, (ax, ax_vol) = plt.subplots(
        2, 1, figsize=(14, 8), height_ratios=[3, 1],
        gridspec_kw={"hspace": 0.05},
    )

    n = len(dates)
    width = 0.6

    # Draw candlesticks
    for i in range(n):
        color = "#26a69a" if closes[i] >= opens[i] else "#ef5350"
        body_bottom = min(opens[i], closes[i])
        body_height = abs(closes[i] - opens[i])
        # Wick
        ax.plot([i, i], [lows[i], highs[i]], color=color, linewidth=0.8)
        # Body
        ax.bar(i, body_height, bottom=body_bottom, width=width,
               color=color, edgecolor=color, linewidth=0.5)

    # Moving averages
    if n >= 5:
        ma5 = _moving_avg(closes, 5)
        ax.plot(range(n), ma5, color="#FF9800", linewidth=1, alpha=0.8, label="MA5")
    if n >= 20:
        ma20 = _moving_avg(closes, 20)
        ax.plot(range(n), ma20, color="#2196F3", linewidth=1, alpha=0.8, label="MA20")
    if n >= 60:
        ma60 = _moving_avg(closes, 60)
        ax.plot(range(n), ma60, color="#9C27B0", linewidth=1, alpha=0.8, label="MA60")

    # Support levels (green dashed)
    for level in support_levels:
        ax.axhline(y=level, color="#4CAF50", linestyle="--", linewidth=1.5, alpha=0.85)
        ax.text(n + 0.5, level, f"S ${level:,.1f}",
                fontsize=9, color="#4CAF50", fontweight="bold", va="center")

    # Resistance levels (red dashed)
    for level in resistance_levels:
        ax.axhline(y=level, color="#F44336", linestyle="--", linewidth=1.5, alpha=0.85)
        ax.text(n + 0.5, level, f"R ${level:,.1f}",
                fontsize=9, color="#F44336", fontweight="bold", va="center")

    # Volume bars
    vol_colors = [
        "#26a69a" if closes[i] >= opens[i] else "#ef5350" for i in range(n)
    ]
    ax_vol.bar(range(n), volumes, width=width, color=vol_colors, alpha=0.6)

    # X-axis date labels
    tick_interval = max(1, n // 10)
    tick_positions = list(range(0, n, tick_interval))
    tick_labels = [dates[i].strftime("%m/%d") for i in tick_positions]
    for a in (ax, ax_vol):
        a.set_xticks(tick_positions)
    ax.set_xticklabels([])
    ax_vol.set_xticklabels(tick_labels, fontsize=8, rotation=45)

    # Styling
    ax.set_title(ticker, fontsize=16, fontweight="bold", pad=10)
    ax.set_ylabel("Price ($)", fontsize=11)
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.2)
    ax.set_xlim(-1, n + 3)
    ax_vol.set_ylabel("Volume", fontsize=9)
    ax_vol.grid(True, alpha=0.2)
    ax_vol.set_xlim(-1, n + 3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _moving_avg(values: list[float], window: int) -> list[float | None]:
    result: list[float | None] = []
    for i in range(len(values)):
        if i < window - 1:
            result.append(None)
        else:
            result.append(sum(values[i - window + 1: i + 1]) / window)
    return result


def _is_number(v) -> bool:
    try:
        float(v)
        return True
    except (ValueError, TypeError):
        return False
