from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI


def build_chat_model(config: dict[str, Any], model_key: str = "model") -> ChatOpenAI:
    model_config = config.get(model_key) or config.get("model")
    if model_config is None:
        raise ValueError(f"Model configuration '{model_key}' is missing.")

    return ChatOpenAI(
        model=model_config["name"],
        api_key=model_config["api_key"],
        base_url=model_config["base_url"],
        temperature=model_config.get("temperature", 0.2),
        max_tokens=model_config.get("max_output_tokens"),
    )
