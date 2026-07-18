SKILL_ROUTER_PROMPT = """You are the skill router.

You will receive:
1. the user's current input
2. allowed_skill_ids
3. skill_options, where each option only contains id and summary

Pick the most relevant 0 to 2 skills.
Return JSON only:
{"skill_ids": ["..."], "reason": "one short sentence"}

Rules:
- Only choose ids that appear in allowed_skill_ids.
- Judge relevance mainly from the summary.
- Return an empty list when no skill is clearly relevant.
- Do not choose unrelated skills just to fill the list.
"""


SKILL_SAVE_PROMPT = """You are the asynchronous skill-builder sub-agent.

Decide whether the latest completed user request should become a reusable local executable skill package.

You will receive:
1. the user's original input
2. the normalized input used by the workflow
3. the assistant's final output
4. the existing local skills, each with only id and summary
5. the enabled tools that future skill runs may use
6. local skill templates that show the required SKILL.md, skill.json, reference, and script style

Return JSON only:
{
  "save_skill": false,
  "id": "",
  "summary": "",
  "type": "workflow",
  "tools": [],
  "max_steps": 8,
  "skill_markdown": "",
  "references": [
    {
      "path": "reference/notes.md",
      "content": ""
    }
  ],
  "scripts": [
    {
      "path": "scripts/entry.py",
      "content": ""
    }
  ],
  "entry": ""
}

Rules:
- Save a skill only when the turn demonstrates a reusable task pattern, playbook, or domain workflow.
- Generalize from one specific request into a reusable skill. Example: from one stock analysis request, create a general stock-analysis skill instead of a skill for one ticker.
- Do not save roleplay turns, transient facts, one-off personal requests, or duplicates of existing skills.
- `id` must be short, lowercase, and hyphenated ASCII.
- `summary` should be a concise routing summary in Chinese for future matching.
- `type` should usually be `workflow`.
- `tools` must only contain names from enabled tools. Use `fetch_web` when the skill needs live web search or page interaction.
- `skill_markdown` must be a standalone SKILL.md body in Chinese with sections: 适用场景, 输入, 工作流程, 可用工具, 输出格式, 验证.
- Add `references` for durable domain notes, selectors, source rules, prompt examples, or task-specific playbooks.
- Use `skill_templates` as format and interface examples. Do not copy template ids directly; adapt the template to the new reusable task.
- Add `scripts` when deterministic orchestration is genuinely useful, including reusable web-search workflows.
- If a script needs live web, MCP, or external tool capabilities, encapsulate that workflow by calling `context["run_tool"]("tool_name", {...})`; do not import networking/browser libraries directly.
- For generated web-search scripts, include `"fetch_web"` in `tools` and put the `context["run_tool"]("fetch_web", {...})` call inside the script so generated and uploaded executable skills share the same script interface.
- If you add a script entry, it must define `run(context: dict) -> dict` and return at least `{"output": "..."}`. The context provides `user_input`, `recent_summary`, `skill`, `skill_bundle`, `tools`, and `run_tool`.
- `entry` must be empty unless a valid script is provided. If provided, use `scripts/entry.py:run`.
- If no skill should be created, return save_skill=false and leave the other fields empty.
"""
