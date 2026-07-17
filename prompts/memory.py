LONG_TERM_MEMORY_PROMPT = """You extract memory updates for a layered memory system.

Based on the current user input and assistant reply, decide whether anything is worth saving.
Return JSON only:
{
  "memory_fact": "",
  "self_update": "",
  "history_event": "",
  "pending_fact": ""
}

Rules:
- memory_fact is for stable user/project facts that may later be merged into MEMORY.md.
- self_update is for behavior, tone, or operating-rule changes that should become active via Redis first and merge into SELF.md only after repeated evidence.
- history_event is for completed actions or decisions; it is written to SQLite HISTORY/audit tables and must not be treated as prompt Markdown memory.
- pending_fact is for unconfirmed clues or preferences; it belongs in Redis and must not be treated as a confirmed fact.
- If same-type facts conflict, keep the newer and more specific statement.
- Do not save raw CQ image codes, transient filler, or duplicate facts.
- Keep each field short. If nothing fits a field, leave it empty.
"""
