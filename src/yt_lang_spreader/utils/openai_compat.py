"""Compatibility helpers for OpenAI chat-completions parameters."""

from __future__ import annotations

from typing import Any


def chat_completion_params(
    *,
    model: str,
    temperature: float | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build chat-completion params, skipping unsupported args by model."""
    params: dict[str, Any] = {"model": model, **kwargs}
    _normalize_token_limit_param(model, params)
    if temperature is not None and _supports_custom_temperature(model):
        params["temperature"] = temperature
    return params


def _supports_custom_temperature(model: str) -> bool:
    """GPT-5 family currently supports only the default temperature."""
    return not model.lower().startswith("gpt-5")


def _normalize_token_limit_param(model: str, params: dict[str, Any]) -> None:
    """Map token-limit args to the model-specific supported parameter name."""
    if not model.lower().startswith("gpt-5"):
        return

    max_tokens = params.pop("max_tokens", None)
    if "max_completion_tokens" not in params and max_tokens is not None:
        params["max_completion_tokens"] = max_tokens
