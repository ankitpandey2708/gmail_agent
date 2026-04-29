# Cross-Session Memory Design

## Storage

Two SQLite tables in `memory.db`:

| Table | Columns | Purpose |
|---|---|---|
| `preferences` | `key`, `value`, `updated_at` | Evergreen user preferences |
| `rolling_summary` | `id`, `content`, `updated_at` | Single compressed context paragraph |

## What Gets Stored

**Preferences** — inferred from behavior, stable across sessions:
- `reply_tone` → `formal` / `casual`
- `auto_trash_categories` → e.g. `promotions`
- `preferred_labels` → labels the user applies often

**Rolling summary** — one paragraph, fixed size (~150 tokens), updated each session:
```
"User prefers formal replies. Regularly trashes promotions.
Frequently searches Flipkart/Amazon orders. Labels finance
emails as 'bills'. Unsubscribed from 3 newsletters."
```

## How It Stays Fixed Size

At session end, the LLM merges the current session into the existing rolling summary — not appended, replaced. No matter how many sessions have passed, the memory blob stays ~150 tokens.

```
existing rolling summary + session activity → LLM compresses → new rolling summary
```

## System Prompt Injection

Memory is injected at `init_chat()` time, under a `## Memory` section:

```
## Memory
Preferences: reply_tone=formal
Context: User prefers formal replies. Regularly trashes promotions...
```

Total overhead: ~200 tokens, constant forever.

## Lifecycle

```
startup  → load preferences + rolling summary → inject into system prompt
session  → normal conversation (no writes)
shutdown → LLM compresses session → update rolling summary + any new preferences
```

## What Is NOT Stored

- Raw email content (privacy)
- Full conversation logs (unbounded growth)
- Individual session history (rolling summary absorbs it)

## Why Not Other Approaches

| Approach | Problem |
|---|---|
| Inject last N summaries | Grows linearly with sessions |
| Full conversation log | Hits context limits, expensive |
| Vector DB | Overkill for single-user, ~365 sessions/year |
| Relevance filtering | Added complexity, not needed at this scale |
