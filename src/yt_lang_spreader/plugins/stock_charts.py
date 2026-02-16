"""Stock chart plotting plugin.

Detects stock ticker mentions in video segments, fetches price data,
and generates annotated charts with support/resistance levels.

Uses yfinance for data and matplotlib for plotting.
"""

from __future__ import annotations

import os
import re

import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

from ..core.models import Segment


# Common patterns for stock tickers in video transcripts
TICKER_PATTERN = re.compile(
    r"""
    (?:^|[\s(])                  # start of string or whitespace/paren
    (?:                          # group: various ticker formats
        \$([A-Z]{1,5})           # $AAPL style
      | (?:ticker|stock|symbol)  # "ticker AAPL" style
        \s*[:=]?\s*
        ([A-Z]{1,5})
    )
    (?:[\s).,;]|$)               # end boundary
    """,
    re.VERBOSE | re.MULTILINE,
)

# Price-related keywords that hint at support/resistance mentions
SUPPORT_KEYWORDS = re.compile(
    r"support(?:\s+(?:level|zone|area|at|around|near))?\s*"
    r"(?:of\s+)?(?:is\s+)?(?:at\s+)?(?:around\s+)?"
    r"\$?([\d,]+\.?\d*)",
    re.IGNORECASE,
)
RESISTANCE_KEYWORDS = re.compile(
    r"resist(?:ance)?(?:\s+(?:level|zone|area|at|around|near))?\s*"
    r"(?:of\s+)?(?:is\s+)?(?:at\s+)?(?:around\s+)?"
    r"\$?([\d,]+\.?\d*)",
    re.IGNORECASE,
)
PRICE_TARGET_KEYWORDS = re.compile(
    r"(?:price\s+)?target\s*(?:of\s+)?(?:is\s+)?(?:at\s+)?(?:around\s+)?"
    r"\$?([\d,]+\.?\d*)",
    re.IGNORECASE,
)


def detect_stock_mentions(segments: list[Segment]) -> dict[int, dict]:
    """Scan segments for stock ticker mentions and price levels.

    Returns:
        dict mapping segment index → {
            "tickers": ["AAPL", ...],
            "support_levels": [150.0, ...],
            "resistance_levels": [180.0, ...],
            "price_targets": [200.0, ...],
        }
    """
    results: dict[int, dict] = {}

    for segment in segments:
        text = segment.text  # scan original transcript (more detail)
        tickers = set()
        support_levels: list[float] = []
        resistance_levels: list[float] = []
        price_targets: list[float] = []

        # Find tickers
        for match in TICKER_PATTERN.finditer(text):
            ticker = match.group(1) or match.group(2)
            if ticker:
                tickers.add(ticker)

        # Find support levels
        for match in SUPPORT_KEYWORDS.finditer(text):
            try:
                val = float(match.group(1).replace(",", ""))
                support_levels.append(val)
            except (ValueError, AttributeError):
                pass

        # Find resistance levels
        for match in RESISTANCE_KEYWORDS.finditer(text):
            try:
                val = float(match.group(1).replace(",", ""))
                resistance_levels.append(val)
            except (ValueError, AttributeError):
                pass

        # Find price targets
        for match in PRICE_TARGET_KEYWORDS.finditer(text):
            try:
                val = float(match.group(1).replace(",", ""))
                price_targets.append(val)
            except (ValueError, AttributeError):
                pass

        if tickers or support_levels or resistance_levels:
            results[segment.index] = {
                "tickers": sorted(tickers),
                "support_levels": support_levels,
                "resistance_levels": resistance_levels,
                "price_targets": price_targets,
            }

    return results


def generate_stock_charts(
    segments: list[Segment],
    output_dir: str,
    period: str = "6mo",
) -> list[Segment]:
    """Generate stock price charts for segments that mention stocks.

    For each segment with detected tickers, fetches historical price data
    and plots a chart with support/resistance annotations.

    Updates each segment's chart_paths in-place.

    Args:
        segments: List of Segment objects (text must be populated).
        output_dir: Directory to save chart images.
        period: yfinance period string (e.g., "3mo", "6mo", "1y").

    Returns:
        Updated segments with chart_paths set.
    """
    os.makedirs(output_dir, exist_ok=True)
    mentions = detect_stock_mentions(segments)

    if not mentions:
        return segments

    # Lazy import — yfinance is only needed when stock charts are requested
    try:
        import yfinance as yf
    except ImportError:
        print(
            "  Warning: yfinance not installed. "
            "Run `pip install yfinance` to enable stock charts."
        )
        return segments

    seg_map = {seg.index: seg for seg in segments}

    for seg_idx, info in mentions.items():
        segment = seg_map.get(seg_idx)
        if segment is None:
            continue

        for ticker in info["tickers"]:
            chart_path = os.path.join(
                output_dir, f"chart_{seg_idx:03d}_{ticker}.png"
            )
            try:
                _plot_stock_chart(
                    ticker=ticker,
                    support_levels=info["support_levels"],
                    resistance_levels=info["resistance_levels"],
                    price_targets=info["price_targets"],
                    period=period,
                    output_path=chart_path,
                )
                segment.chart_paths.append(chart_path)
            except Exception as e:
                print(f"  Warning: Could not generate chart for {ticker}: {e}")

    return segments


def _plot_stock_chart(
    ticker: str,
    support_levels: list[float],
    resistance_levels: list[float],
    price_targets: list[float],
    period: str,
    output_path: str,
) -> None:
    """Fetch stock data and create an annotated price chart."""
    import yfinance as yf

    data = yf.download(ticker, period=period, progress=False)
    if data.empty:
        raise ValueError(f"No data returned for ticker '{ticker}'")

    # Handle multi-level columns from yfinance
    if hasattr(data.columns, "levels") and len(data.columns.levels) > 1:
        data.columns = data.columns.get_level_values(0)

    fig, ax = plt.subplots(figsize=(12, 6))

    # Price line
    ax.plot(data.index, data["Close"], color="#2196F3", linewidth=1.5, label="Close")

    # Moving averages
    if len(data) >= 20:
        ma20 = data["Close"].rolling(window=20).mean()
        ax.plot(data.index, ma20, color="#FF9800", linewidth=1, alpha=0.7, label="MA20")
    if len(data) >= 50:
        ma50 = data["Close"].rolling(window=50).mean()
        ax.plot(data.index, ma50, color="#9C27B0", linewidth=1, alpha=0.7, label="MA50")

    # Support levels (green dashed)
    for level in support_levels:
        ax.axhline(
            y=level, color="#4CAF50", linestyle="--", linewidth=1.5, alpha=0.8
        )
        ax.annotate(
            f"Support ${level:,.2f}",
            xy=(data.index[-1], level),
            xytext=(10, -5),
            textcoords="offset points",
            fontsize=9,
            color="#4CAF50",
            fontweight="bold",
        )

    # Resistance levels (red dashed)
    for level in resistance_levels:
        ax.axhline(
            y=level, color="#F44336", linestyle="--", linewidth=1.5, alpha=0.8
        )
        ax.annotate(
            f"Resistance ${level:,.2f}",
            xy=(data.index[-1], level),
            xytext=(10, 5),
            textcoords="offset points",
            fontsize=9,
            color="#F44336",
            fontweight="bold",
        )

    # Price targets (gold dotted)
    for target in price_targets:
        ax.axhline(
            y=target, color="#FFC107", linestyle=":", linewidth=1.5, alpha=0.8
        )
        ax.annotate(
            f"Target ${target:,.2f}",
            xy=(data.index[-1], target),
            xytext=(10, 0),
            textcoords="offset points",
            fontsize=9,
            color="#FFC107",
            fontweight="bold",
        )

    # Volume bars on a twin axis
    ax2 = ax.twinx()
    colors = [
        "#4CAF50" if c >= o else "#F44336"
        for c, o in zip(data["Close"], data["Open"])
    ]
    ax2.bar(data.index, data["Volume"], color=colors, alpha=0.15, width=1)
    ax2.set_ylabel("Volume", fontsize=9, alpha=0.5)
    ax2.tick_params(axis="y", labelsize=8, colors="gray")

    # Styling
    ax.set_title(f"{ticker} — Stock Price Analysis", fontsize=14, fontweight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("Price ($)", fontsize=11)
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate()

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
