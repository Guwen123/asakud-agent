# NiceEval Integration Notes

NiceEval is a good fit for higher-level agent scenario tests once the local JSONL cases are stable.

## Recommended Use

- Multi-step scenario testing.
- Agent trajectory checks.
- Browser/web-agent scenarios.
- Regression tests for workflows such as fetch_web, reminders, and skill execution.

## Suggested Project Shape

```text
test/
|-- cases/
|   `-- agent_eval_cases.jsonl
|-- niceeval/
|   |-- niceeval.config.ts
|   `-- agents/
|       `-- asakud-agent.ts
```

## Adapter Idea

Expose one adapter that calls the local backend:

```ts
export async function askAsakudAgent(input: string) {
  const response = await fetch("http://127.0.0.1:8000/getMessage", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      post_type: "message",
      message_type: "private",
      user_id: 10001,
      message: input,
      self_id: 99999
    })
  });
  return await response.json();
}
```

## Notes

Do not start with NiceEval as the only eval layer. Keep this repository's Python local runner as the fast sanity check, then use NiceEval for richer agent scenarios.
