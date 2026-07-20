from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_loop.nodes.skills import (
    load_runtime_skill_registry,
    load_skill_bundle,
    load_skill_registry,
    persist_generated_skill,
)


class SkillRegistryTests(unittest.TestCase):
    def test_load_skill_registry_normalizes_and_filters_entries(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asakud-skill-test-") as temp_dir:
            root = Path(temp_dir)
            skill_config = root / "skill.config.md"
            skill_file = root / "skills" / "boss" / "SKILL.md"
            skill_file.parent.mkdir(parents=True)
            skill_file.write_text("# Boss Search\n\nUse this skill.", encoding="utf-8")
            payload = {
                "skills": [
                    {
                        "id": "Boss Search",
                        "summary": "Search Boss jobs.",
                        "path": str(skill_file),
                        "enabled": True,
                    },
                    {
                        "id": "Boss Search",
                        "summary": "Duplicate should be ignored.",
                        "path": str(skill_file),
                        "enabled": True,
                    },
                    {
                        "id": "disabled-skill",
                        "summary": "Hidden at runtime.",
                        "path": str(skill_file),
                        "enabled": False,
                    },
                    {
                        "id": "missing-summary",
                        "path": str(skill_file),
                    },
                ]
            }
            skill_config.write_text(
                "# Skill Registry\n\n```json\n"
                + json.dumps(payload, ensure_ascii=False, indent=2)
                + "\n```\n",
                encoding="utf-8",
            )
            config = {"paths": {"skill_config_file": str(skill_config)}}

            all_skills = load_skill_registry(config)
            runtime_skills = load_runtime_skill_registry(config)

            self.assertEqual([item["id"] for item in all_skills], ["boss-search", "disabled-skill"])
            self.assertEqual([item["id"] for item in runtime_skills], ["boss-search"])

    def test_load_skill_bundle_includes_references(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asakud-skill-test-") as temp_dir:
            root = Path(temp_dir)
            skill_dir = root / "skills" / "stock"
            reference_dir = skill_dir / "reference"
            reference_dir.mkdir(parents=True)
            skill_path = skill_dir / "SKILL.md"
            skill_path.write_text("# Stock Lookup\n\nMain instruction.", encoding="utf-8")
            (reference_dir / "rules.md").write_text("Use official quote pages.", encoding="utf-8")
            registry = [
                {
                    "id": "stock-lookup",
                    "summary": "Lookup stocks.",
                    "path": str(skill_path),
                    "references": ["reference/rules.md"],
                    "enabled": True,
                }
            ]
            config = {"paths": {"skill_config_file": str(root / "missing.md")}}

            bundle = load_skill_bundle(config, "stock-lookup", registry=registry)

            self.assertIn("Main instruction", bundle)
            self.assertIn("Extra Reference: reference/rules.md", bundle)
            self.assertIn("Use official quote pages", bundle)

    def test_persist_generated_skill_writes_safe_script_and_registry(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asakud-skill-test-") as temp_dir:
            root = Path(temp_dir)
            config = {
                "paths": {
                    "skills_dir": str(root / "skills"),
                    "skill_config_file": str(root / "skills" / "skill.config.md"),
                },
                "tools": {"enabled": ["fetch_web"]},
            }
            payload = {
                "save_skill": True,
                "id": "Boss Search",
                "summary": "Search Boss jobs.",
                "skill_markdown": "Search job postings and summarize role requirements.",
                "tools": ["fetch_web", "mcp"],
                "scripts": [
                    {
                        "path": "scripts/entry.py",
                        "content": "def run(task, context=None):\n    return {'ok': True, 'task': task}\n",
                    }
                ],
                "entry": "scripts/entry.py:run",
            }

            entry = persist_generated_skill(config, payload)

            self.assertEqual(entry["id"], "boss-search")
            self.assertEqual(entry["tools"], ["fetch_web"])
            self.assertEqual(entry["entry"], "scripts/entry.py:run")
            self.assertTrue((root / "skills" / "generated" / "boss-search" / "SKILL.md").exists())
            self.assertTrue((root / "skills" / "generated" / "boss-search" / "scripts" / "entry.py").exists())
            self.assertTrue((root / "skills" / "skill.config.md").exists())

    def test_persist_generated_skill_filters_blocked_script(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asakud-skill-test-") as temp_dir:
            root = Path(temp_dir)
            config = {
                "paths": {
                    "skills_dir": str(root / "skills"),
                    "skill_config_file": str(root / "skills" / "skill.config.md"),
                },
                "tools": {"enabled": ["fetch_web"]},
            }
            payload = {
                "save_skill": True,
                "id": "Unsafe Skill",
                "summary": "Should filter unsafe script.",
                "skill_markdown": "Do not keep unsafe script.",
                "scripts": [
                    {
                        "path": "scripts/entry.py",
                        "content": "def run(task, context=None):\n    os.system('echo bad')\n",
                    }
                ],
                "entry": "scripts/entry.py:run",
            }

            entry = persist_generated_skill(config, payload)

            self.assertEqual(entry["id"], "unsafe-skill")
            self.assertNotIn("entry", entry)
            self.assertFalse((root / "skills" / "generated" / "unsafe-skill" / "scripts" / "entry.py").exists())


if __name__ == "__main__":
    unittest.main()
