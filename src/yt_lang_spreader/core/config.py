"""Centralized configuration for the entire pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PipelineConfig:
    """All settings for a pipeline run, gathered in one place."""

    # --- Input ---
    url: str = ""

    # --- Language ---
    source_lang: str = "auto"
    target_lang: str = "zh"

    # --- Summarization ---
    target_length_minutes: float | None = None  # None = no summarization (keep full)

    # --- Segmentation ---
    num_segments: int | None = None
    segment_duration: float = 120.0  # seconds

    # --- Key frames ---
    frames_per_segment: int = 3

    # --- Narration / TTS ---
    tts_backend: str = "gtts"  # "gtts" | "elevenlabs" | "openai_tts" | "local"
    elevenlabs_voice_id: str = ""
    elevenlabs_model: str = "eleven_multilingual_v2"
    openai_tts_voice: str = "alloy"
    local_voice_dir: str = ""  # dir with pre-recorded wav/mp3 per segment

    # --- Subtitle generation ---
    generate_subtitles: bool = True  # generate SRT/VTT for YouTube CC
    subtitle_formats: list[str] = field(default_factory=lambda: ["srt", "vtt"])

    # --- Video output ---
    show_subtitles: bool = True  # burn-in subtitle overlay on video
    video_size: tuple[int, int] = (1280, 720)

    # --- Plugins ---
    enable_stock_charts: bool = False  # auto-detect and plot stock charts

    # --- Stock data API ---
    stock_api: str = "longport"  # "longport" | "yfinance"
    longport_app_key: str = ""
    longport_app_secret: str = ""
    longport_access_token: str = ""

    # --- OpenAI ---
    openai_api_key: str = ""

    # --- Models ---
    text_model: str = "gpt-5-mini"        # segmentation, summarization, translation, slides, vision
    speech_model: str = "tts-1-hd"         # OpenAI TTS narration
    transcript_model: str = "whisper-1"    # audio transcription fallback

    # --- ElevenLabs ---
    elevenlabs_api_key: str = ""

    # --- Output ---
    output_dir: str = "output"
    keep_temp: bool = False

    # --- Debug mode ---
    debug: bool = False

    @staticmethod
    def _load_dotenv() -> dict[str, str]:
        """Load simple KEY=VALUE pairs from .env if present."""
        candidates = [
            Path.cwd() / ".env",
            Path(__file__).resolve().parents[3] / ".env",
        ]

        for dotenv_path in candidates:
            if not dotenv_path.exists():
                continue

            values: dict[str, str] = {}
            for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if not key:
                    continue
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                values[key] = value

            if values:
                return values

        return {}

    def resolve_api_keys(self) -> None:
        """Fill in API keys from environment variables when not set explicitly."""
        dotenv_values = self._load_dotenv()

        if not self.openai_api_key:
            self.openai_api_key = (
                os.environ.get("OPENAI_API_KEY", "")
                or dotenv_values.get("OPENAI_API_KEY", "")
            )
        if not self.elevenlabs_api_key:
            self.elevenlabs_api_key = (
                os.environ.get("ELEVENLABS_API_KEY", "")
                or dotenv_values.get("ELEVENLABS_API_KEY", "")
            )
        if not self.longport_app_key:
            self.longport_app_key = (
                os.environ.get("LONGPORT_APP_KEY", "")
                or dotenv_values.get("LONGPORT_APP_KEY", "")
            )
        if not self.longport_app_secret:
            self.longport_app_secret = (
                os.environ.get("LONGPORT_APP_SECRET", "")
                or dotenv_values.get("LONGPORT_APP_SECRET", "")
            )
        if not self.longport_access_token:
            self.longport_access_token = (
                os.environ.get("LONGPORT_ACCESS_TOKEN", "")
                or dotenv_values.get("LONGPORT_ACCESS_TOKEN", "")
            )
