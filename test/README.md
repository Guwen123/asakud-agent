# asakud-agent Evaluation

This directory contains the local evaluation system for `asakud-agent`.

The goal is not to prove that every answer is perfect. The goal is to catch workflow regressions early: wrong tool usage, reminder mistakes, memory boundary errors, style leakage, Skill routing issues, and web-search instability.

## Evaluation Layers

| Layer | Command | Purpose | Requires LLM |
| --- | --- | --- | --- |
| Unit tests | `python -m unittest discover -s test -p "test_*.py"` | Test local evaluators, config loading, recent summary, Skill registry/generation | No |
| Static checks | `python test\run_static_checks.py` | Validate config, DB schema, memory files, registries, tools, and prompt contract | No |
| Local contract eval | `python test\run_agent_eval.py` | Run JSONL cases through the Agent and assert output/debug constraints | Yes |
| LangSmith eval | `python test\run_langsmith_eval.py` | Upload selected JSONL cases to LangSmith and run Agent experiments with code evaluators | Yes + LangSmith |
| Network eval | `python test\run_agent_eval.py --include-network` | Include browser/web-search cases | Yes + network |
| Side-effect eval | `python test\run_agent_eval.py --include-side-effects` | Include reminder/memory cases that write local state | Yes |
| Observability | Langfuse / LangSmith | Trace trajectories, latency, tool calls, human review, judge scores | Optional |
| Scenario eval | NiceEval | Higher-level multi-step scenario tests | Optional |

Recommended order:

1. Run static checks after every refactor.
2. Run unit tests for local deterministic logic.
3. Run safe local contract evals before committing.
4. Run side-effect and network cases before larger demos.
5. Use Langfuse/LangSmith/NiceEval after local evals are stable.

## Commands

Validate static project contracts:

```powershell
python test\run_static_checks.py
```

Run deterministic unit tests:

```powershell
python -m unittest discover -s test -p "test_*.py"
```

Validate case syntax only:

```powershell
python test\run_agent_eval.py --dry-run
```

Run safe local evals:

```powershell
python test\run_agent_eval.py
```

Run one case:

```powershell
python test\run_agent_eval.py --case-id skill_runner_path
```

Run one category:

```powershell
python test\run_agent_eval.py --category reminder --include-side-effects
```

Run all local cases:

```powershell
python test\run_agent_eval.py --include-network --include-side-effects
```

Results are written to `test/results/*.jsonl` and `test/results/*.md`.

Run LangSmith evaluation:

```powershell
$env:LANGSMITH_API_KEY="lsv2_..."
python test\run_langsmith_eval.py --dry-run
python test\run_langsmith_eval.py
```

Run LangSmith side-effect/network cases:

```powershell
python test\run_langsmith_eval.py --include-side-effects --include-network
```

The script creates a timestamped LangSmith dataset from the selected JSONL cases, runs the Agent as the target function, and records evaluator scores such as `contract_assertions`, `has_message`, `latency_seconds`, `trace_total_seconds`, `node_total_seconds`, `tool_total_seconds`, `model_total_seconds`, and token metrics.

## Case Schema

Each row in `test/cases/agent_eval_cases.jsonl` is one JSON object:

```json
{
  "id": "reminder_daily_medicine",
  "category": "reminder",
  "input": "每天晚上八点提醒我吃药。",
  "message_target": {
    "message_type": "private",
    "user_id": 10001
  },
  "requires": ["side_effects"],
  "side_effects": true,
  "assertions": {
    "must_contain_any": [["提醒", "记下", "创建"], ["20:00", "八点"]],
    "tool_calls_must_contain_any": [["create_reminder"]],
    "must_not_contain": ["SCHEDULED_TASKS"],
    "max_chars": 1000,
    "max_tool_steps": 4
  }
}
```

Supported assertions:

- `must_contain`: every listed token must appear in `message`.
- `must_contain_any`: each group must have at least one token appear in `message`.
- `must_not_contain`: listed tokens must not appear in `message`.
- `must_match_regex`: every regex must match `message`.
- `must_not_match_regex`: listed regex patterns must not match `message`.
- `min_chars` / `max_chars`: response length bounds.
- `image_ref`: expected image reference string.
- `tool_calls_must_contain`: every listed tool must be called.
- `tool_calls_must_contain_any`: each group must include at least one called tool.
- `tool_calls_must_not_contain`: listed tools must not be called.
- `max_tool_steps`: maximum LangGraph tool-loop iterations.
- `recent_summary_loaded`: whether `RECENT_SUMMARY` was loaded into this turn.

Local Markdown reports also include `Trace ms`, `Tool ms`, and `Model ms` columns from `debug.performance`.

## What This Evaluates

Current case coverage:

- Basic response quality and no internal metadata leakage.
- Reminder requests create structured SQLite reminders.
- Long-term preference updates are not confused with reminders.
- Web-search tasks route through `fetch_web`.
- MCP configuration questions are answered without unnecessary tool calls.
- Skill execution model is explained consistently with `SkillRunnerAgent`.

## External Evaluation

Use `test/metrics/rubric.md` as the shared scoring rubric for Langfuse, LangSmith, NiceEval, or manual review.

Langfuse is best for production-like traces, dataset comparison, human review, and judge scoring.

LangSmith is best for debugging LangGraph/LangChain trajectories and tool-call arguments.

NiceEval is best for multi-step scenarios after the local JSONL cases are already stable.
