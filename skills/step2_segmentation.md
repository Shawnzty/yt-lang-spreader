# Step 2: Semantic Segmentation

## Purpose
Split the transcript into semantic segments based on topic boundaries. Each segment is classified by type (macro / index / stock) with extracted tickers and price levels.

## Current Behavior
- Sends the full timestamped transcript to GPT in a single call
- GPT identifies topic boundaries and classifies each segment
- Extracts tickers (e.g. NVDA, SPY, QQQ) and support/resistance price levels
- Falls back to time-based segmentation if GPT fails

## LLM Usage
- **Model**: `text_model` (default `gpt-5-mini`)
- **Temperature**: 0.1 (deterministic)
- **Calls**: 1 per video
- **System prompt**: Financial video transcript analyst role. Segments by topic_type: macro, index, stock. Extracts tickers, support_levels, resistance_levels.
- **User prompt**: Video title + full timestamped transcript. Asks for JSON array of segments.

## Input
- `step1_download/video_info.json` — subtitles, duration, title

## Output
Saved to `stepN_segmentation/`:
- `segments.json` — array of segment objects with: index, start, end, text, topic_type, topic_label, tickers, support_levels, resistance_levels

## Topic Types
- **macro**: General market news, Fed meetings, interest rates, geopolitics, earnings overview
- **index**: Market indices — S&P 500, NASDAQ, SOX/SOXX, Dow Jones, Russell 2000
- **stock**: Individual stock analysis — NVDA, AAPL, TSLA, etc.

## Instructions
<!-- Customize this section to control segmentation behavior -->
<!-- Examples: how to handle ambiguous topics, minimum segment length, -->
<!-- specific tickers to watch for, how to classify certain discussions -->
