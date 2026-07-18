from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "agent.config.md"
CONFIG_BLOCK_PATTERN = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
MODEL_CONFIG_KEYS = ("main_model", "route_model", "multimodal_model")
MODEL_USER_INPUT_FIELDS = ("base_url", "api_key")


def project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return ROOT / path


def load_config(config_path: str | Path = DEFAULT_CONFIG_PATH, *, expand_env: bool = True) -> dict[str, Any]:
    path = project_path(config_path)
    text = path.read_text(encoding="utf-8")

    if path.suffix.lower() == ".json":
        data = json.loads(text)
        return _runtime_config(data, expand_env=expand_env)

    if path.suffix.lower() == ".md":
        match = CONFIG_BLOCK_PATTERN.search(text)
        if not match:
            raise ValueError(f"No fenced json config block found in {path}")
        data = json.loads(match.group(1))
        return _runtime_config(data, expand_env=expand_env)

    raise ValueError(f"Unsupported config file type: {path.suffix}")


def load_raw_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    return load_config(config_path, expand_env=False)


def _expand_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, str):
        return ENV_PATTERN.sub(lambda match: os.getenv(match.group(1), match.group(0)), value)
    return value


def _runtime_config(data: dict[str, Any], *, expand_env: bool) -> dict[str, Any]:
    if not expand_env:
        return data
    expanded = _expand_env(data)
    _restore_model_user_input_fields(expanded, data)
    return expanded


def _restore_model_user_input_fields(expanded: dict[str, Any], raw: dict[str, Any]) -> None:
    for model_key in MODEL_CONFIG_KEYS:
        raw_model = raw.get(model_key)
        expanded_model = expanded.get(model_key)
        if not isinstance(raw_model, dict) or not isinstance(expanded_model, dict):
            continue
        for field in MODEL_USER_INPUT_FIELDS:
            if field in raw_model:
                expanded_model[field] = raw_model[field]
