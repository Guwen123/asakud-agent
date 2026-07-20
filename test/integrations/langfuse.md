# Langfuse Integration Notes

Use Langfuse after local contract tests are stable.

## Recommended Use

- Trace real conversations from staging/production.
- Create datasets from good and bad traces.
- Run offline experiments against fixed datasets.
- Attach LLM-as-judge or code evaluators for correctness, tool discipline, and style leakage.

## Environment Variables

```powershell
set LANGFUSE_PUBLIC_KEY=...
set LANGFUSE_SECRET_KEY=...
set LANGFUSE_HOST=https://cloud.langfuse.com
```

## Suggested Scores

- `correctness`
- `tool_discipline`
- `reminder_discipline`
- `memory_discipline`
- `style_safety`
- `latency_seconds`
- `tool_step_count`

## Minimal Flow

1. Run `python test\run_agent_eval.py --output test\results\local_eval.jsonl`.
2. Upload or mirror the JSONL results into a Langfuse dataset/experiment.
3. Add LLM-as-judge using `test/metrics/rubric.md`.
4. Promote production traces into new regression cases when a bug appears.

## Notes

Keep local deterministic assertions as the first gate. Langfuse should be the observability and experiment layer, not the only source of truth.
