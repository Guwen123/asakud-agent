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


def project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return ROOT / path


def load_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    path = project_path(config_path)
    text = path.read_text(encoding="utf-8")

    if path.suffix.lower() == ".json":
        return _expand_env(json.loads(text))

    if path.suffix.lower() == ".md":
        match = CONFIG_BLOCK_PATTERN.search(text)
        if not match:
            raise ValueError(f"No fenced json config block found in {path}")
        return _expand_env(json.loads(match.group(1)))

    raise ValueError(f"Unsupported config file type: {path.suffix}")


def _expand_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, str):
        return ENV_PATTERN.sub(lambda match: os.getenv(match.group(1), match.group(0)), value)
    return value
