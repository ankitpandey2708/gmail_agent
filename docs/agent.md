# Gmail Agent Debug Session

## What this is
A Python terminal Gmail agent that takes plain-English commands, uses a Gemini/Gemma LLM in a ReAct loop, and executes Gmail operations via IMAP/SMTP. I want you to help me debug issues with agent behaviour, search quality, and output quality.

---

## Architecture

### Flow
```
User types query
  → run_agent() stores raw message in _current_user_message
  → LLM receives message + SYSTEM_PROMPT + TOOL_DECLARATIONS
  → LLM decides which tool to call
  → tool_search_emails() called
      → _search_with_fallback(agent_query, original=_current_user_message)
          → _rewrite_queries(agent_query, original) — separate LLM call, thinking OFF, temp=0
              → generates 3 IMAP query variants
              → tries each in order via _imap_search()
              → returns first batch that has results
      → fetches email headers from IMAP (body NOT fetched yet — lazy)
      → stores in session_emails dict
      → returns summary string with ID, From, Subject, Date, Labels
  → LLM calls get_email_body(email_id) if it needs content
      → fetches body from IMAP
      → runs through _strip_html (BeautifulSoup) + _clean_email_text (regex)
      → cached in session_emails
  → LLM produces final answer wrapped in <answer>...</answer> tags
  → run_agent() extracts answer text and prints it
```

### Key components

**`_rewrite_queries(user_query, original)`**
- Receives: agent's reformulated query + original raw user message
- Generates 3 query variants:
  - Q1: `from:domain.com subject:keyword` (most precise)
  - Q2: single operator fallback
  - Q3: free text fallback
- Tries each in order, returns first that has results

**`_imap_search(query)`**
- Wraps everything in `X-GM-RAW "query -in:spam -in:trash"`
- Pure IMAP flags (ALL, UNSEEN, SEEN, FLAGGED) bypass X-GM-RAW

**`_clean_email_text(text)`**
- Removes quoted reply chains, signatures, footer boilerplate, bare URLs
- Runs on both plain text and HTML emails (HTML goes through BeautifulSoup first)

**`session_emails`**
- In-memory dict keyed by IMAP email ID
- Stores: id, from, subject, date, labels, body (lazy), list_unsubscribe headers
- Persists for the session; `clear` command resets it

**`generationConfig`**
- Main agent: `temperature=0`, `max_output_tokens=1024`
- Rewriter: `temperature=0`, `max_output_tokens=200`

---

## Tools (12 total)

| Tool | Purpose |
|---|---|
| `search_emails(query, limit)` | IMAP search, returns metadata summary |
| `get_email_body(email_id)` | Fetch + clean body of specific email |
| `get_thread(email_id)` | Fetch full conversation thread |
| `parse_attachment(email_id)` | Extract text from PDF/image attachments |
| `trash_email(email_id)` | Move to trash (requires y/n approval) |
| `apply_label(email_id, label)` | Apply Gmail label |
| `mark_read(email_id)` | Mark as read |
| `mark_unread(email_id)` | Mark as unread |
| `draft_reply(email_id, draft_body)` | Draft + send reply (requires approval) |
| `http_request(url, method, ...)` | HTTP GET/POST — used for RFC 8058 unsubscribe |
| `create_calendar_event(...)` | Opens pre-filled Google Calendar URL in browser |
| `suggest_new_tool(description, example)` | Logs capability gaps to JSON file |

---

## Known issues / what I'm debugging