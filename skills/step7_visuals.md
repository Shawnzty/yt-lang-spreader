# Step 7: Visual Generation

## Purpose
Generate visual assets tailored to each segment's topic type: info slides for macro topics, candlestick charts for index/stock topics.

## Current Behavior

### Macro segments → Info Slides
- Uses GPT to extract structured bullet points from transcript
- Renders presentation-style slides with Pillow: dark navy background, title + bullets
- Falls back to sentence splitting if GPT fails
- Slide style: accent blue bars, white title, light gray bullets

### Index/Stock segments → Candlestick Charts
- Fetches OHLCV data from Longport API (default) or yfinance (fallback)
- Uses GPT Vision on extracted key frames to refine support/resistance levels
- Plots: candlestick bars, MA5/MA20/MA60, volume, S/R annotations (green/red dashed lines)

## LLM Usage

### Slide bullet extraction (macro segments)
- **Model**: `text_model` (default `gpt-5-mini`)
- **Temperature**: 0.2
- **Calls**: 1 per macro segment
- **Prompt**: Extracts key information into slide format — title + 3-6 bullets (<60 chars each). Returns JSON array.

### S/R Vision analysis (index/stock segments)
- **Model**: `text_model` (used for vision)
- **Temperature**: 0
- **Calls**: 1 per index/stock segment (up to 3 frames analyzed)
- **Prompt**: Reads charts from video screenshots. Extracts support and resistance price levels. Returns JSON with support/resistance arrays.

## Input
- `step6_keyframes/segments.json` — segments with frame_paths, tickers, topic_type

## Output
Saved to `stepN_visuals/`:
- `segments.json` — segments with `slide_paths` and `chart_paths` populated
- `slides/slide_001_00.png`, ... — generated info slides
- `charts/chart_001_NVDA.png`, ... — generated candlestick charts

## Instructions
<!-- Customize this section to control visual generation -->
<!-- Examples: slide color scheme, chart time period, which MAs to show, -->
<!-- how to format S/R labels, preferred chart style -->
