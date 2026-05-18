from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI


def build_chat_model(
    config: dict[str, Any],
    model_key: str = "model",
    overrides: dict[str, Any] | None = None,
) -> ChatOpenAI:
    model_config = config.get(model_key) or config.get("model")
    if model_config is None:
        raise ValueError(f"Model configuration '{model_key}' is missing.")
    merged = dict(model_config)
    if overrides:
        merged.update(overrides)

    return ChatOpenAI(
        model=merged["name"],
        api_key=merged["api_key"],
        base_url=merged["base_url"],
        temperature=merged.get("temperature", 0.2),
        max_tokens=merged.get("max_output_tokens"),
    )
