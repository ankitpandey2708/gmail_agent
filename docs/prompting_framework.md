# Agent Prompting Framework

MECE rules for splitting instructions between system prompt and tool declarations.
Apply this framework whenever adding a new tool or editing existing prompts.

---

## The core rule

| Layer | Owns | Does NOT own |
|---|---|---|
| **System prompt** | Agent behaviour, reasoning, workflow sequencing, response format | Tool-specific syntax, parameter constraints, tool selection conditions |
| **Tool declarations** | Tool contract (what it does, when to pick it, parameter rules) | Workflow ordering, multi-tool chains, post-call behaviour instructions |

---

## System prompt — what belongs here

### 1. Agent identity and global behaviour
Who the agent is, what it should do by default, tone, response format.

```
Act immediately on read tasks. Ask a clarifying question only when intent is
ambiguous AND the action is irreversible. One question maximum.
```

### 2. Workflow sequencing (multi-tool chains)
Any rule that involves calling tool A before tool B, or conditioning tool C on the result of tool B.

```
Always call search_emails first — you need IDs before acting.
Always try get_email_body before parse_attachment.
search → get_email_body → extract → respond.
```

### 3. Batch/bulk consent logic
The pattern for obtaining user confirmation before a loop belongs here, not spread across individual tool descriptions.

```
For batch tasks: search, show summary (count + senders), ask once
"Proceed with all N?" — do not begin the loop until confirmed.
Once confirmed, call trash_emails_bulk with the full ID list.
```

### 4. Post-call behaviour
What the agent should do after calling a specific tool (e.g. report back to the user).

```
After calling suggest_new_tool, tell the user what capability was logged.
```

### 5. Output format constraints
Tags, structure, tone rules.

```
Wrap your final answer in <answer>...</answer> tags. No exceptions.
```

---

## Tool declarations — what belongs here

### 1. What the tool does (1 sentence)
Clear, verb-first description of the tool's purpose.

```
"Search emails in inbox/all mail. Excludes spam and trash."
"Move a single email to trash."
```

### 2. When to pick this tool over another (selection conditions)
Disambiguation between tools with overlapping purposes.

```
"For spam/trash/sent/drafts use search_folder instead."
"Use this whenever the user mentions a folder by name."
```

### 3. Parameter contracts
Type, valid values, format constraints, examples. This is the only place for syntax rules.

```
query: "Gmail search syntax. Do not quote operator values:
        write from:company not from:'company'."
skip_confirm: "Set true only after explicit bulk user consent. Default false."
```

### 4. Output format (if non-obvious)
What the tool returns and how to interpret it.

```
"Returns ID, From, Subject, Date, Labels per email. Use IDs for follow-up calls."
```

### 5. Hard limitations of the tool itself
Rate limits, payload caps, data format restrictions intrinsic to the tool.

```
"Maximum 1000 records per request."
```

---

## Anti-patterns

| Anti-pattern | Example | Fix |
|---|---|---|
| Workflow logic in tool description | `"ALWAYS call this first"` in search_emails | Move to system prompt |
| Tool syntax in system prompt | `"Do not quote operator values"` in system prompt | Move to query parameter description |
| Duplicate instructions | Same rule in system prompt AND tool description | Single source — pick the right layer |
| Post-call behaviour in tool description | `"Always tell the user what was logged"` in suggest_new_tool | Move to system prompt |
| Chaining rules in tool description | `"Only call this if get_email_body fails"` in parse_attachment | Move to system prompt as a sequencing rule |
| Tool selection in system prompt | `"call trash_emails_bulk after confirmation"` in system prompt | Move to tool declaration as selection condition |
| Ambiguous output format instruction | `"wrap your final answer"` — excludes questions in model's interpretation | Say "ALL user-facing text including questions and confirmations" |
| Output format in wrong section | `<answer>` tag rule inside `## Completing tasks` | Move to its own `## Output` section |
| Vague tool purpose | `"Performs operations on emails"` | Rewrite as verb-first: `"Move a single email to trash."` |

---

## Checklist before adding a new tool

- [ ] Tool description: 1–3 sentences, verb-first, covers purpose + selection condition
- [ ] Each parameter: type, valid values, format constraints — no workflow logic
- [ ] Any multi-tool chain involving this tool: added to system prompt, not tool description
- [ ] Any post-call behaviour: added to system prompt
- [ ] No instruction appears in both system prompt and tool description
- [ ] Run ruff + vulture after changes
