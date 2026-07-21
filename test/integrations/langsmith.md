# LangSmith Evaluation

`asakud-agent` uses LangSmith as the observable experiment layer for Agent evaluation.

Local JSONL cases remain the source of truth. `test/run_langsmith_eval.py` maps each case into a LangSmith dataset example, runs the Agent as the target function, and records code-evaluator scores.

## What Gets Uploaded

Each JSONL case becomes a LangSmith example:

```json
{
  "inputs": {
    "case_id": "reminder_daily_medicine",
    "category": "reminder",
    "input": "每天晚上八点提醒我吃药。",
    "message_target": {
      "message_type": "private",
      "user_id": 10001
    },
    "requires": ["side_effects"],
    "side_effects": true
  },
  "outputs": {
    "assertions": {
      "tool_calls_must_contain_any": [["create_reminder"]]
    },
    "notes": "Should create a daily reminder."
  }
}
```

## Evaluators

Implemented evaluators:

- `contract_assertions`: reuses local assertions from `test/evaluators.py`, including response content, forbidden leakage, tool-call requirements, and max tool steps.
- `has_message`: checks whether the Agent produced a non-empty user-facing answer.
- `latency_seconds`: records local target function latency as a numeric metric.
- `performance_trace_present`: checks whether `debug.performance` was preserved in the final Agent output.
- `trace_total_ms`: records total LangGraph workflow trace duration.
- `node_total_ms`, `tool_total_ms`, `model_total_ms`: break latency down by workflow nodes, tool calls, and model calls.
- `slowest_node_ms`, `slowest_tool_ms`, `slowest_model_ms`: expose bottlenecks with the slowest component name as the evaluator comment.
- `actual_total_tokens`, `estimated_total_tokens`: record token usage when available, with local estimates as fallback visibility.

## Run

```powershell
pip install -r requirements.txt
$env:LANGSMITH_API_KEY="lsv2_..."
python test\run_langsmith_eval.py --dry-run
python test\run_langsmith_eval.py
```

Include side-effect and network cases only when you intentionally want them:

```powershell
python test\run_langsmith_eval.py --include-side-effects --include-network
```

## Notes

- The script creates timestamped datasets to avoid mutating older experiment baselines.
- Reminder side-effect cases are cleaned up by default.
- Agent outputs include optional debug payloads so LangSmith can inspect tool calls and workflow state.
- Keep local unit/static tests as the first gate; use LangSmith for trace inspection, experiment comparison, and reviewable evaluation history.
