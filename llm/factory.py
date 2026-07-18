from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI

MAIN_MODEL_KEY = "main_model"
ROUTE_MODEL_KEY = "route_model"
MULTIMODAL_MODEL_KEY = "multimodal_model"

LEGACY_MODEL_KEYS = {
    MAIN_MODEL_KEY: "model",
}


def build_chat_model(
    config: dict[str, Any],
    model_key: str = MAIN_MODEL_KEY,
    overrides: dict[str, Any] | None = None,
) -> ChatOpenAI:
    model_config = config.get(model_key)
    if model_config is None:
        legacy_key = LEGACY_MODEL_KEYS.get(model_key)
        if legacy_key:
            model_config = config.get(legacy_key)
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


def build_route_model(config: dict[str, Any], overrides: dict[str, Any] | None = None) -> ChatOpenAI:
    return build_chat_model(config, model_key=ROUTE_MODEL_KEY, overrides=overrides)


def build_multimodal_model(config: dict[str, Any], overrides: dict[str, Any] | None = None) -> ChatOpenAI:
    return build_chat_model(config, model_key=MULTIMODAL_MODEL_KEY, overrides=overrides)
