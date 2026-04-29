# Search Latency Optimizations

MECE breakdown of latency in `tool_search_emails` and concrete optimizations
for each component. Latency decomposes into four mutually exclusive buckets;
each optimization slots into exactly one.

## Latency components

1. **Rewriter LLM round-trip** — `_rewrite_queries()` calls Gemini to
   generate IMAP query variants.
2. **IMAP search round-trip(s)** — sequential `_imap_search()` calls until
   one returns hits.
3. **Header fetch** — `_batch_fetch_headers()` over matched UIDs.
4. **Result formatting** — negligible.

---

## A. Eliminate the work (skip the call)

Best ROI — zero work is faster than fast work.

| #  | Optimization                                                                                                      | Applies to   |
| -- | ----------------------------------------------------------------------------------------------------------------- | ------------ |
| A1 | Bypass rewriter when query already contains Gmail operators (`from:`, `subject:`, `is:`, `has:`, `newer_than:`, `older_than:`, `category:`) | Rewriter     |
| A2 | Skip IMAP search entirely when answer is in `session_emails` cache                                                | IMAP         |

## B. Reduce work per call (make each call cheaper)

Cut tokens, model size, and decode constraints.

| #  | Optimization                                                                  | Applies to   |
| -- | ----------------------------------------------------------------------------- | ------------ |
| B1 | Use Flash-Lite model for rewriter only (keep main `MODEL` for ReAct loop)     | Rewriter     |
| B2 | Set `thinking_level=DISABLED` on rewriter                                     | Rewriter     |
| B3 | Use `response_schema=list[str]` (constrained decoding) instead of regex parse | Rewriter     |
| B4 | Generate 2 variants instead of 3                                              | Rewriter     |
| B5 | Default `limit=25` on `search_emails` to bound header-fetch                   | Header fetch |

## C. Parallelize the work (overlap independent calls)

Sum-of-N → max-of-N when calls don't depend on each other.

| #  | Optimization                                                                                | Applies to |
| -- | ------------------------------------------------------------------------------------------- | ---------- |
| C1 | Fire all rewritten IMAP queries concurrently via `ThreadPoolExecutor`; take first non-empty | IMAP       |

## D. Reuse the work (cache prior results)

Pay once, hit forever.

| #  | Optimization                                                                | Applies to |
| -- | --------------------------------------------------------------------------- | ---------- |
| D1 | In-memory dict cache keyed on `hash(intent.lower().strip())` → cached variants | Rewriter   |
| D2 | Gemini prompt caching — low payoff at ~200-token prompt size (optional)     | Rewriter   |

---

## Coverage check (collectively exhaustive)

| Latency component         | Covered by                       |
| ------------------------- | -------------------------------- |
| Rewriter LLM round-trip   | A1, B1, B2, B3, B4, D1, D2       |
| IMAP search round-trip(s) | A2, C1                           |
| Header fetch              | B5                               |
| Result formatting         | (negligible — not optimized)     |

## Mutual exclusivity check

- **A** removes the call → **B/C/D** never run for that path.
- **B** shrinks a call that **A** decided to make.
- **C** parallelizes calls that **A** and **B** already minimized.
- **D** short-circuits everything above on cache hit (orthogonal to A–C
  since cache is checked first).

---

## Recommended execution order

Highest leverage first:

1. **A1 + B2** — one-line wins, ~50% median latency drop.
2. **D1** — 5 lines, makes repeat queries instant.
3. **C1** — ~20 lines, eliminates worst-case sequential fallback.
4. **B1, B3, B4, B5** — model/config tweaks, modest gains.
5. **A2, D2** — diminishing returns.

---

## References

- [Gemini 3.1 Flash-Lite Preview](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite-preview)
- [Gemini 3 Developer Guide — thinking budget](https://ai.google.dev/gemini-api/docs/gemini-3)
- [Fast JSON Decoding for Local LLMs (LMSYS)](https://www.lmsys.org/blog/2024-02-05-compressed-fsm/)
- [Optimize LLM cost and latency with caching (AWS)](https://aws.amazon.com/blogs/database/optimize-llm-response-costs-and-latency-with-effective-caching/)
- [LLM Token Optimization (Redis)](https://redis.io/blog/llm-token-optimization-speed-up-apps/)
- [Query Rewriting via LLMs (arXiv)](https://arxiv.org/html/2502.12918v1)
