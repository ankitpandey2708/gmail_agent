"""
Triage action helpers for the Triage UI tab.
Called by app.py event handlers — no UI logic here.
"""
import json
import os
import re
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google.genai import types

import config
from tools import ensure_connected, fetch_msg, get_body, _select_entry_folder

TRIAGE_LOG_FILE = "triage_log.json"
SEND_QUEUE_FILE = "send_queue.json"


# ── Decision log ───────────────────────────────────────────────────────────────


def log_decision(email_id: str, subject: str, sender: str, action: str) -> None:
    log = _load_json(TRIAGE_LOG_FILE)
    log.append({
        "email_id": email_id,
        "subject": subject,
        "sender": sender,
        "action": action,
        "timestamp": datetime.now().isoformat(),
    })
    _save_json(TRIAGE_LOG_FILE, log)


def load_decisions() -> list:
    return _load_json(TRIAGE_LOG_FILE)


# ── Draft generation ───────────────────────────────────────────────────────────


def fetch_email_body(email_id: str) -> str:
    try:
        ensure_connected()
        with _select_entry_folder(email_id):
            msg = fetch_msg(email_id)
            return get_body(msg)[:1500]
    except Exception as ex:
        return f"(could not fetch body: {ex})"


def generate_draft(email: dict) -> tuple:
    """Returns (draft_text, usage_dict)."""
    body = fetch_email_body(email["id"])
    prompt = (
        f"Write a concise, professional reply to this email.\n"
        f"FROM: {email.get('from', '')}\n"
        f"SUBJECT: {email.get('subject', '')}\n\n"
        f"BODY:\n{body}\n\n"
        "Rules:\n"
        "- Max 3 short paragraphs\n"
        "- Friendly but direct — address the key ask\n"
        "- No closing signature\n"
        "- Plain text only\n\n"
        "Write ONLY the reply body, nothing else."
    )
    try:
        resp = config.ensure_client().models.generate_content(
            model=config.MODEL,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=512,
                thinking_config=types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.MINIMAL
                ),
            ),
            contents=prompt,
        )
        usage = _extract_usage(resp)
        return resp.text.strip(), usage
    except Exception as ex:
        return f"(draft generation failed: {ex})", {}


def edit_draft(draft: str, instruction: str) -> tuple:
    """Returns (draft_text, usage_dict)."""
    prompt = (
        f"Edit this email draft per the instruction below.\n\n"
        f"DRAFT:\n{draft}\n\n"
        f"INSTRUCTION: {instruction}\n\n"
        "Reply ONLY with the revised draft text, nothing else."
    )
    try:
        resp = config.ensure_client().models.generate_content(
            model=config.MODEL,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=512,
                thinking_config=types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.MINIMAL
                ),
            ),
            contents=prompt,
        )
        return resp.text.strip(), _extract_usage(resp)
    except Exception:
        return draft, {}


# ── Gmail actions ──────────────────────────────────────────────────────────────


def archive_in_gmail(email_id: str) -> None:
    """Remove from INBOX by expunging — keeps email in All Mail (= Gmail archive)."""
    ensure_connected()
    config.mail.select("INBOX")
    config.mail.uid("store", email_id.encode(), "+FLAGS", "\\Deleted")
    config.mail.expunge()
    config.mail.select('"[Gmail]/All Mail"')


# ── Send queue ─────────────────────────────────────────────────────────────────


def add_to_send_queue(email: dict, draft: str) -> None:
    send_q = _load_json(SEND_QUEUE_FILE)
    send_q.append({
        "email_id": email["id"],
        "to": _extract_reply_to(email),
        "subject": _make_reply_subject(email.get("subject", "")),
        "body": draft,
        "in_reply_to": email.get("message_id", ""),
        "references": email.get("references", ""),
        "approved_at": datetime.now().isoformat(),
    })
    _save_json(SEND_QUEUE_FILE, send_q)


def load_send_queue() -> list:
    return _load_json(SEND_QUEUE_FILE)


def dispatch_all() -> tuple:
    send_q = _load_json(SEND_QUEUE_FILE)
    if not send_q:
        return 0, []

    sent, errors, remaining = 0, [], []
    for item in send_q:
        try:
            msg = MIMEMultipart()
            msg["From"] = config.EMAIL
            msg["To"] = item["to"]
            msg["Subject"] = item["subject"]
            if item.get("in_reply_to"):
                msg["In-Reply-To"] = item["in_reply_to"]
                refs = item.get("references", "")
                msg["References"] = f"{refs} {item['in_reply_to']}".strip() if refs else item["in_reply_to"]
            msg.attach(MIMEText(item["body"], "plain"))
            with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as srv:
                srv.starttls()
                srv.login(config.EMAIL, config.APP_PASSWORD)
                srv.send_message(msg)
            sent += 1
        except Exception as ex:
            errors.append(str(ex))
            remaining.append(item)

    _save_json(SEND_QUEUE_FILE, remaining)
    return sent, errors


# ── Learn loop ─────────────────────────────────────────────────────────────────


def run_learn_loop() -> tuple:
    decisions = load_decisions()
    if len(decisions) < 5:
        return {"error": "Need at least 5 decisions to analyse.", "rules": [], "insights": ""}, {}

    summary = "\n".join(
        f"{d['action'].upper()}: {d['sender']} | {d['subject']}"
        for d in decisions[-100:]
    )

    prompt = (
        "Analyse these email triage decisions and suggest new filter rules.\n\n"
        + summary
        + "\n\nReturn a JSON object:\n"
        '{"insights": "2-3 sentence summary of patterns",\n'
        ' "rules": [\n'
        '   {"type": "archiveSenderPatterns"|"archiveSubjectPatterns"|"spamSubjectPatterns",\n'
        '    "pattern": "regex or string",\n'
        '    "reason": "why this pattern makes sense"}\n'
        " ]}\n\n"
        "Only suggest rules for clear repeated patterns (3+ similar decisions)."
    )
    try:
        resp = config.ensure_client().models.generate_content(
            model=config.MODEL,
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=1024,
                thinking_config=types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.MINIMAL
                ),
            ),
            contents=prompt,
        )
        usage = _extract_usage(resp)
        m = re.search(r"\{.*\}", resp.text.strip(), re.DOTALL)
        if m:
            return json.loads(m.group()), usage
        return {"error": "Could not parse LLM response.", "rules": [], "insights": ""}, usage
    except Exception as ex:
        return {"error": str(ex), "rules": [], "insights": ""}, {}


def apply_learned_rules(new_rules: list) -> int:
    from pipeline import load_rules, save_rules
    rules = load_rules()
    added = 0
    for r in new_rules:
        rtype = r.get("type")
        pattern = r.get("pattern", "").strip()
        if rtype in rules and pattern and pattern not in rules[rtype]:
            rules[rtype].append(pattern)
            added += 1
    if added:
        save_rules(rules)
    return added


# ── Private helpers ────────────────────────────────────────────────────────────


def _extract_usage(resp) -> dict:
    meta = getattr(resp, "usage_metadata", None)
    return {
        "input":  getattr(meta, "prompt_token_count",     0) or 0,
        "output": getattr(meta, "candidates_token_count", 0) or 0,
    }


def _load_json(path: str) -> list:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def _save_json(path: str, data) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _extract_reply_to(email: dict) -> str:
    return email.get("reply_to") or email.get("from", "")


def _make_reply_subject(subject: str) -> str:
    return subject if re.match(r"re:", subject, re.IGNORECASE) else f"Re: {subject}"


def extract_name(addr: str) -> str:
    """'Alice Chen <alice@example.com>' → 'Alice Chen'"""
    m = re.match(r'^"?([^"<]+)"?\s*<', addr)
    if m:
        return m.group(1).strip()
    m = re.match(r"^([^@]+)@", addr)
    if m:
        return m.group(1).replace(".", " ").title()
    return addr
