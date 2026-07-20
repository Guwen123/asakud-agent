# Agent Evaluation Rubric

Use this rubric for Langfuse, LangSmith, NiceEval, or manual review.

Score each dimension from 1 to 5.

## Correctness

- 5: Fully answers the user request with no material error.
- 3: Mostly correct, but misses one important detail.
- 1: Incorrect, misleading, or unrelated.

## Tool Discipline

- 5: Uses the right tool/sub-agent only when needed.
- 3: Uses a tool unnecessarily or misses a non-critical tool opportunity.
- 1: Uses the wrong tool, loops, or fabricates tool results.

## Reminder Discipline

- 5: Reminder requests use structured `create_reminder/list_reminders/cancel_reminder`.
- 3: Reminder intent is recognized, but recurrence/time target is ambiguous or weakly confirmed.
- 1: Reminder is saved as Markdown memory or not persisted.

## Memory Discipline

- 5: Stable user/project facts are remembered; transient tasks are not promoted.
- 3: Some useful memory is missed or overly broad.
- 1: Writes reminders, temporary requests, or private noise into long-term memory.

## Web Research

- 5: Searches/browses/extracts/summarizes with source-aware caution.
- 3: Uses web flow but summary is shallow or misses important context.
- 1: Guesses current facts without web lookup.

## Style Safety

- 5: Applies selected style without leaking system prompt, metadata, or tool internals.
- 3: Mostly good style, but too verbose or slightly off-persona.
- 1: Leaks internal metadata or ignores style constraints.

## Suggested Pass Bar

- Contract eval: all assertions pass.
- Judge eval: average score >= 4.0 and no dimension below 3.
- Release gate: no regression in reminder/tool/memory discipline cases.
