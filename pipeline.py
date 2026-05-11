"""
Three-layer email triage pipeline.
  Layer 1 — IMAP query:    inbox, unread, newer_than:14d   (~200 threads)
  Layer 2 — Rule engine:   triage_rules.json patterns      (~100 survive)
  Layer 3 — LLM classify:  Gemini batch classify           (~40 survive)
  Output  — Two JSON queues: queue_reply.json / queue_info.json
"""
import json
import os
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from google.genai import types

import config
from tools import (
    ensure_connected,
    _batch_fetch_headers,
    fetch_msg,
    get_body,
    _select_entry_folder,
)

RULES_FILE = "triage_rules.json"
QUEUE_REPLY_FILE = "queue_reply.json"
QUEUE_INFO_FILE = "queue_info.json"

_DEFAULT_RULES = {
    "archiveSenderPatterns": [
        "noreply",
        "no-reply",
        "donotreply",
        "do-not-reply",
        "notifications@",
        "notify@",
        "digest@",
        "newsletter@",
        "mailer@",
        "bounce@",
        "calendar-notification@google.com",
        "invitations-noreply@linkedin.com",
        "comments-.*@email.figma.com",
        "notify@mail.notion.so",
    ],
    "archiveSubjectPatterns": [
        r"has (accepted|declined) your invitation",
        r"invited you to",
        r"(weekly|monthly|daily) (digest|report|roundup)",
        r"newsletter",
        r"your (receipt|order|payment|subscription)",
        r"order (confirmation|shipped|delivered|processing)",
        r"payment (confirmed|processed|received)",
        r"(new|added) comment",
        r"merged|closed|opened|pushed to",
    ],
    "archiveDomainPatterns": [
        "linkedin.com",
        "twitter.com",
        "facebook.com",
        "instagram.com",
    ],
    "spamSubjectPatterns": [
        "exploring collaboration",
        "hire top tech talent",
        "gentle follow-up",
        "strategic partnership",
        "quick question",
        "touching base",
        "circling back",
        "hope this finds you well",
        "mutual benefit",
        "synergies",
    ],
}


# ── Rules ──────────────────────────────────────────────────────────────────────


def load_rules() -> dict:
    if not os.path.exists(RULES_FILE):
        with open(RULES_FILE, "w") as f:
            json.dump(_DEFAULT_RULES, f, indent=2)
        return _DEFAULT_RULES
    with open(RULES_FILE) as f:
        return json.load(f)


def save_rules(rules: dict) -> None:
    with open(RULES_FILE, "w") as f:
        json.dump(rules, f, indent=2)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _relative_time(date_str: str) -> str:
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = datetime.now(timezone.utc) - dt
        secs = diff.total_seconds()
        if secs < 3600:
            return f"{int(secs // 60)}m"
        if secs < 86400:
            return f"{int(secs // 3600)}h"
        if secs < 604800:
            return f"{int(secs // 86400)}d"
        return f"{int(secs // 604800)}w"
    except Exception:
        return ""


def _matches_any(text: str, patterns: list) -> bool:
    text = text.lower()
    for p in patterns:
        try:
            if re.search(p.lower(), text):
                return True
        except re.error:
            if p.lower() in text:
                return True
    return False


# ── Layer 1: IMAP fetch ────────────────────────────────────────────────────────


def _layer1_fetch(limit: int = 200) -> list:
    ensure_connected()
    config.mail.select("INBOX")
    _, data = config.mail.uid("search", None, 'X-GM-RAW "is:unread newer_than:14d"')
    ids = data[0].split()
    if not ids:
        config.mail.select('"[Gmail]/All Mail"')
        return []

    ids = ids[-limit:]
    headers = _batch_fetch_headers(ids)
    results = []
    for mid in ids:
        h = headers.get(mid, {})
        if not h:
            continue
        mid_str = mid.decode()
        entry = {
            "id": mid_str,
            "from": h.get("from", ""),
            "subject": h.get("subject", ""),
            "date": h.get("date", ""),
            "message_id": h.get("message_id", ""),
            "in_reply_to": h.get("in_reply_to", ""),
            "references": h.get("references", ""),
            "thread_id": h.get("thread_id", ""),
            "labels": h.get("labels", []),
            "list_unsubscribe": h.get("list_unsubscribe", ""),
            "folder": "INBOX",
            "relative_time": _relative_time(h.get("date", "")),
            "thread_count": 1,
        }
        config.session_emails[mid_str] = dict(entry)
        results.append(entry)

    config.mail.select('"[Gmail]/All Mail"')
    return results


# ── Layer 2: Rule engine ───────────────────────────────────────────────────────


def _layer2_filter(emails: list, rules: dict) -> tuple:
    archive_senders = rules.get("archiveSenderPatterns", [])
    archive_subjects = rules.get("archiveSubjectPatterns", [])
    archive_domains = rules.get("archiveDomainPatterns", [])
    spam_subjects = rules.get("spamSubjectPatterns", [])

    surviving, filtered = [], 0
    for e in emails:
        sender = e.get("from", "").lower()
        subject = e.get("subject", "").lower()
        domain_m = re.search(r"@([\w.-]+)", sender)
        domain = domain_m.group(1) if domain_m else ""

        if e.get("list_unsubscribe"):
            filtered += 1
            continue
        if _matches_any(sender, archive_senders):
            filtered += 1
            continue
        if _matches_any(subject, archive_subjects + spam_subjects):
            filtered += 1
            continue
        if domain and _matches_any(domain, archive_domains):
            filtered += 1
            continue

        surviving.append(e)

    return surviving, filtered


# ── Thread counts ──────────────────────────────────────────────────────────────


def _enrich_thread_counts(emails: list) -> None:
    ensure_connected()
    config.mail.select('"[Gmail]/All Mail"')
    for e in emails:
        tid = e.get("thread_id", "")
        if not tid:
            continue
        try:
            _, data = config.mail.uid("search", None, f"X-GM-THRID {tid}")
            e["thread_count"] = len(data[0].split())
        except Exception:
            pass


# ── Layer 3: LLM classify ─────────────────────────────────────────────────────


def _layer3_classify(emails: list) -> tuple:
    if not emails:
        return [], [], {"input_tokens": 0, "output_tokens": 0}

    # Fetch body snippet for each email (latest message, max 400 chars)
    ensure_connected()
    for e in emails:
        try:
            with _select_entry_folder(e["id"]):
                msg = fetch_msg(e["id"])
                e["_snippet"] = get_body(msg)[:400]
        except Exception:
            e["_snippet"] = ""

    # Build batch prompt
    items = []
    for i, e in enumerate(emails):
        items.append(
            f"[{i}] FROM: {e['from']}\n"
            f"SUBJECT: {e['subject']}\n"
            f"DATE: {e['date']}\n"
            f"BODY: {e['_snippet'][:300]}"
        )

    prompt = (
        "You are an email triage assistant. Classify each email below.\n"
        "Reply ONLY with a JSON array, one object per email, no prose:\n"
        '[{"index":0,"category":"needs_reply","priority":"high","reason":"..."}]\n\n'
        "category values:\n"
        "  needs_reply   — sender is waiting on the recipient; action required\n"
        "  informational — FYI, no reply needed\n"
        "  noise         — bulk, automated, or irrelevant\n\n"
        "priority values:\n"
        "  high   — urgent / deadline / blocked / financial\n"
        "  normal — everything else\n\n"
        "reason: one tight sentence — why it needs action or why it's noise.\n\n"
        + "\n---\n".join(items)
    )

    try:
        resp = config.ensure_client().models.generate_content(
            model=config.MODEL,
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=2048,
                thinking_config=types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.MINIMAL
                ),
            ),
            contents=prompt,
        )

        usage = {
            "input_tokens": getattr(resp.usage_metadata, "prompt_token_count", 0) or 0,
            "output_tokens": getattr(resp.usage_metadata, "candidates_token_count", 0) or 0,
        }

        m = re.search(r"\[.*\]", resp.text.strip(), re.DOTALL)
        if not m:
            return [], [_strip_snippet(e) for e in emails], usage

        reply_q, info_q = [], []
        for c in json.loads(m.group()):
            idx = c.get("index", -1)
            if not (0 <= idx < len(emails)):
                continue
            e = _strip_snippet(dict(emails[idx]))
            e["category"] = c.get("category", "informational")
            e["priority"] = c.get("priority", "normal")
            e["reason"] = c.get("reason", "")
            if e["category"] == "needs_reply":
                reply_q.append(e)
            elif e["category"] == "informational":
                info_q.append(e)

        # High priority first
        _sort_by_priority(reply_q)
        _sort_by_priority(info_q)
        return reply_q, info_q, usage

    except Exception as ex:
        fallback = [_strip_snippet(dict(e)) for e in emails]
        return [], fallback, {"input_tokens": 0, "output_tokens": 0, "error": str(ex)}


def _strip_snippet(e: dict) -> dict:
    e.pop("_snippet", None)
    return e


def _sort_by_priority(lst: list) -> None:
    lst.sort(key=lambda e: 0 if e.get("priority") == "high" else 1)


# ── Queue I/O ──────────────────────────────────────────────────────────────────


def save_queues(reply_queue: list, info_queue: list) -> None:
    with open(QUEUE_REPLY_FILE, "w") as f:
        json.dump(reply_queue, f, indent=2)
    with open(QUEUE_INFO_FILE, "w") as f:
        json.dump(info_queue, f, indent=2)


def load_queues() -> tuple:
    reply, info = [], []
    if os.path.exists(QUEUE_REPLY_FILE):
        with open(QUEUE_REPLY_FILE) as f:
            reply = json.load(f)
    if os.path.exists(QUEUE_INFO_FILE):
        with open(QUEUE_INFO_FILE) as f:
            info = json.load(f)
    return reply, info


# ── Orchestrator ───────────────────────────────────────────────────────────────


def run_pipeline(limit: int = 200) -> dict:
    """Run full three-layer pipeline. Returns stats dict."""
    t0 = time.perf_counter()
    stats = {
        "layer1_count": 0,
        "layer2_filtered": 0,
        "layer2_surviving": 0,
        "layer3_reply": 0,
        "layer3_info": 0,
        "layer3_noise": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "elapsed": 0.0,
        "ran_at": datetime.now().isoformat(),
        "error": None,
    }

    try:
        emails = _layer1_fetch(limit)
        stats["layer1_count"] = len(emails)

        if not emails:
            save_queues([], [])
            stats["elapsed"] = round(time.perf_counter() - t0, 2)
            return stats

        rules = load_rules()
        surviving, filtered = _layer2_filter(emails, rules)
        stats["layer2_filtered"] = filtered
        stats["layer2_surviving"] = len(surviving)

        _enrich_thread_counts(surviving)

        reply_q, info_q, usage = _layer3_classify(surviving)
        stats["layer3_reply"] = len(reply_q)
        stats["layer3_info"] = len(info_q)
        stats["layer3_noise"] = len(surviving) - len(reply_q) - len(info_q)
        stats["input_tokens"] = usage.get("input_tokens", 0)
        stats["output_tokens"] = usage.get("output_tokens", 0)

        save_queues(reply_q, info_q)

    except Exception as ex:
        stats["error"] = str(ex)

    stats["elapsed"] = round(time.perf_counter() - t0, 2)
    return stats
