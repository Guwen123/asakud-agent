from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from agent_loop.config_loader import load_config
from run_static_checks import run_checks


class ConfigAndStaticCheckTests(unittest.TestCase):
    def test_model_user_input_fields_are_not_env_expanded(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asakud-config-test-") as temp_dir:
            config_path = Path(temp_dir) / "agent.config.md"
            config_path.write_text(
                """# Config

```json
{
  "main_model": {
    "name": "main",
    "base_url": "${MODEL_BASE_URL}",
    "api_key": "${MODEL_API_KEY}"
  },
  "route_model": {
    "name": "route",
    "base_url": "${MODEL_BASE_URL}",
    "api_key": "${MODEL_API_KEY}"
  },
  "multimodal_model": {
    "name": "multi",
    "base_url": "${MODEL_BASE_URL}",
    "api_key": "${MODEL_API_KEY}"
  },
  "redis": {
    "url": "${REDIS_URL}"
  }
}
```
""",
                encoding="utf-8",
            )
            old_env = {
                "MODEL_BASE_URL": os.environ.get("MODEL_BASE_URL"),
                "MODEL_API_KEY": os.environ.get("MODEL_API_KEY"),
                "REDIS_URL": os.environ.get("REDIS_URL"),
            }
            os.environ["MODEL_BASE_URL"] = "https://llm.example.com/v1"
            os.environ["MODEL_API_KEY"] = "secret-key"
            os.environ["REDIS_URL"] = "redis://example/0"
            try:
                config = load_config(config_path)
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

            self.assertEqual(config["main_model"]["base_url"], "${MODEL_BASE_URL}")
            self.assertEqual(config["main_model"]["api_key"], "${MODEL_API_KEY}")
            self.assertEqual(config["redis"]["url"], "redis://example/0")

    def test_static_checks_have_no_failures_in_current_project(self) -> None:
        results = run_checks(strict_models=False)
        failures = [item for item in results if item.status == "fail"]

        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
