import calendar
import contextlib
import functools
import imaplib
import smtplib
import email
import re
import os
import json
import webbrowser
import urllib.parse
import requests
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import parsedate
from datetime import datetime
from google.genai import types

import config
from ui import cprint, _esc, _RULE_W, approve, _approve_draft


# ── Error handling ─────────────────────────────────────────────────────────────


def err(ex) -> str:
    return f"Error: {ex}"


def _catch_errors(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except TypeError as ex:
            return f"Error: argument error: {ex}"
        except Exception as ex:
            return err(ex)

    return wrapper


# ── IMAP connection ────────────────────────────────────────────────────────────


def connect_imap() -> None:
    config.mail = imaplib.IMAP4_SSL(config.IMAP_SERVER)
    config.mail.login(config.EMAIL, config.APP_PASSWORD)
    config.mail.select('"[Gmail]/All Mail"')


def ensure_connected() -> None:
    try:
        config.mail.noop()
    except Exception:
        connect_imap()


# ── Email parsing helpers ──────────────────────────────────────────────────────


def decode_subject(raw) -> str:
    if not raw:
        return "(no subject)"
    result = ""
    for part, enc in decode_header(raw):
        if isinstance(part, bytes):
            try:
                result += part.decode(enc or "utf-8", errors="ignore")
            except (LookupError, TypeError):
                result += part.decode("utf-8", errors="ignore")
        else:
            result += part
    return result.strip()


@contextlib.contextmanager
def _select_entry_folder(email_id: str):
    """Select the IMAP folder where this email lives, then restore All Mail.
    UIDs in IMAP are folder-scoped, so any uid() call must run against the
    correct mailbox or it returns nothing / errors.
    """
    folder = (
        config.session_emails.get(email_id, {}).get("folder") or '"[Gmail]/All Mail"'
    )
    config.mail.select(folder)
    try:
        yield folder
    finally:
        config.mail.select('"[Gmail]/All Mail"')


def fetch_msg(mid) -> email.message.Message:
    """Fetch a raw email by ID (bytes or str) and parse it."""
    if isinstance(mid, str):
        mid = mid.encode()
    _, msg_data = config.mail.uid("fetch", mid, "(RFC822)")
    # imaplib responses are inconsistent:
    #   Typical:  [(b'1 (RFC822 {size}', b'...raw email...'), b')']
    #   Edge case: [b'1 (RFC822 {size}', b'...raw email...', b')']
    # Blind indexing bytes[1] gives an int in Python3 → crash on .decode()
    for part in msg_data:
        if isinstance(part, tuple):
            return email.message_from_bytes(part[1])
    body = max((p for p in msg_data if isinstance(p, bytes)), key=len, default=b"")
    if len(body) < 20:
        raise ValueError(f"Invalid FETCH response for {mid!r}: no email body found")
    return email.message_from_bytes(body)


def get_part(msg, *content_types) -> str:
    if msg.is_multipart():
        for ct in content_types:
            for part in msg.walk():
                if part.get_content_type() == ct:
                    return part.get_payload(decode=True).decode(errors="ignore")
    payload = msg.get_payload(decode=True)
    return payload.decode(errors="ignore") if payload else ""


def _strip_html(html_text: str) -> str:
    from bs4 import BeautifulSoup

    return BeautifulSoup(html_text, "html.parser").get_text(separator=" ").strip()


def _clean_email_text(text: str) -> str:
    """
    Compress email text after HTML stripping for LLM consumption.
    Removes email-specific noise — no signal lost, tokens saved.
    Typical reduction: 50-70% for threaded emails, 20-30% for single emails.
    """
    # Quoted reply chains (Gmail / Outlook / Apple Mail)
    text = re.sub(r"On .{10,100}wrote:.*", "", text, flags=re.DOTALL)
    text = re.sub(r"^>+.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"From:.*?Subject:.*?\n", "", text, flags=re.DOTALL)

    # Signatures
    text = re.sub(r"\n--\s*\n.*", "", text, flags=re.DOTALL)
    text = re.sub(
        r"(Best regards|Kind regards|Warm regards|Thanks and regards|"
        r"Regards|Thanks|Thank you|Cheers|Sincerely|Yours truly)"
        r"[,.]?\s*\n.*",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(
        r"Sent from my (iPhone|iPad|Android|Samsung|phone|mobile).*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Footer boilerplate
    text = re.sub(
        r"(Unsubscribe|To unsubscribe|You received this|"
        r"You're receiving this|This email was sent to|"
        r"If you no longer wish|Privacy Policy|Terms of Service|"
        r"© \d{4}|All rights reserved|DISCLAIMER|"
        r"This message is intended|Confidentiality Notice).*",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Bare URLs (tracking pixels, CDN links)
    text = re.sub(r"https?://\S+", "", text)

    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)

    return text.strip()


def _get_entry(email_id: str) -> dict:
    return config.session_emails.get(email_id, {})


def get_body(msg) -> str:
    plain = get_part(msg, "text/plain")
    if plain.strip():
        return _clean_email_text(plain)
    html_body = get_part(msg, "text/html")
    return _clean_email_text(_strip_html(html_body)) if html_body else ""


def _send_smtp(
    to: str, subject: str, body: str, in_reply_to: str = "", references: str = ""
) -> None:
    msg = MIMEMultipart()
    msg["From"] = config.EMAIL
    msg["To"] = to
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = (
            f"{references} {in_reply_to}".strip() if references else in_reply_to
        )
    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
        server.starttls()
        server.login(config.EMAIL, config.APP_PASSWORD)
        server.send_message(msg)


def _append_tool_log(entry: dict) -> None:
    log = []
    if os.path.exists(config.UNKNOWN_TOOLS_LOG):
        with open(config.UNKNOWN_TOOLS_LOG) as f:
            log = json.load(f)
    log.append(entry)
    with open(config.UNKNOWN_TOOLS_LOG, "w") as f:
        json.dump(log, f, indent=2)


# ── IMAP search helpers ────────────────────────────────────────────────────────

_PURE_IMAP = {
    "ALL",
    "SEEN",
    "UNSEEN",
    "FLAGGED",
    "UNFLAGGED",
    "ANSWERED",
    "UNANSWERED",
    "DELETED",
    "UNDELETED",
    "DRAFT",
    "UNDRAFT",
    "NEW",
    "OLD",
    "RECENT",
}
_IMAP_FOLDERS = {
    "spam": '"[Gmail]/Spam"',
    "trash": '"[Gmail]/Trash"',
    "sent": '"[Gmail]/Sent Mail"',
    "draft": '"[Gmail]/Drafts"',
    "drafts": '"[Gmail]/Drafts"',
    "starred": '"[Gmail]/Starred"',
    "inbox": "INBOX",
}


def _fmt_date(raw: str) -> str:
    """'Thu, 13 Nov 2025 18:48:24 +0530 (IST)' → '13 Nov 2025 18:48'"""
    try:
        t = parsedate(raw)
        if t:
            return (
                f"{t[2]:02d} {calendar.month_abbr[t[1]]} {t[0]} {t[3]:02d}:{t[4]:02d}"
            )
    except Exception:
        pass
    return raw.split("(")[0].strip()


def _to_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, bytes):
        return val.decode(errors="ignore")
    if isinstance(val, (tuple, list)):
        return " ".join(_to_str(v) for v in val)
    return str(val)


def _filter_labels(labels: list) -> list:
    return [lbl for lbl in labels if not lbl.startswith("\\")]


def _clean_field(s) -> str:
    return str(s).replace("\r", " ").replace("\n", " ").strip()


def _batch_fetch_headers(ids: list) -> dict:
    """
    Fetch From/Subject/Date/unsubscribe headers + X-GM-LABELS for all IDs
    in a single IMAP round trip. Returns dict keyed by bytes ID.
    """
    if not ids:
        return {}
    id_set = b",".join(ids)
    _, data = config.mail.uid(
        "fetch",
        id_set,
        "(UID BODY.PEEK[HEADER.FIELDS (FROM TO CC REPLY-TO SUBJECT DATE MESSAGE-ID"
        " IN-REPLY-TO REFERENCES CONTENT-TYPE"
        " LIST-UNSUBSCRIBE LIST-UNSUBSCRIBE-POST)] X-GM-LABELS X-GM-THRID)",
    )
    results = {}
    for item in data:
        if not isinstance(item, tuple):
            continue
        meta = _to_str(item[0])
        m_uid = re.search(r"\bUID (\d+)\b", meta)
        if not m_uid:
            continue
        mid = m_uid.group(1).encode()
        labels = []
        m_lbl = re.search(r"X-GM-LABELS \((.+?)\)", meta)
        if m_lbl:
            labels = m_lbl.group(1).split()
        thread_id = ""
        m_thr = re.search(r"X-GM-THRID (\d+)", meta)
        if m_thr:
            thread_id = m_thr.group(1)
        msg = email.message_from_bytes(item[1])
        results[mid] = {
            "from": msg["From"] or "",
            "to": msg["To"] or "",
            "cc": msg["Cc"] or "",
            "reply_to": msg["Reply-To"] or "",
            "subject": decode_subject(msg["Subject"]),
            "date": _fmt_date(msg["Date"] or ""),
            "message_id": msg["Message-ID"] or "",
            "in_reply_to": msg["In-Reply-To"] or "",
            "references": msg["References"] or "",
            "content_type": msg.get_content_type() or "",
            "labels": _filter_labels(labels),
            "list_unsubscribe": msg.get("List-Unsubscribe", "") or "",
            "list_unsubscribe_post": msg.get("List-Unsubscribe-Post", "") or "",
            "thread_id": thread_id,
        }
    return results


def _imap_search(query: str):
    """
    Execute a single IMAP search against [Gmail]/All Mail.
    Pure flags (ALL, UNSEEN etc.) → pass directly.
    Everything else → X-GM-RAW with spam/trash excluded.
    For folder-specific searches use tool_search_folder.
    """
    clean = query.replace('"', "").strip()
    if clean.upper() in _PURE_IMAP:
        return config.mail.uid("search", None, clean)
    return config.mail.uid("search", None, f'X-GM-RAW "{clean} -in:spam -in:trash"')


def _rewrite_queries(user_query: str, original: str = "") -> list:
    """
    Rewrite-Retrieve-Read: translate natural language into email-optimised
    IMAP queries. Accepts original user message for raw intent context.
    """
    intent = original.strip() if original.strip() else user_query
    try:
        resp = config.client.models.generate_content(
            model=config.MODEL,
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=200,
                thinking_config=types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.MINIMAL
                ),
            ),
            contents=(
                "You are an email search query rewriter. "
                "Convert the user intent into 3 Gmail IMAP search queries. "
                "Rules:\n"
                "- Use terms that appear in email subjects/bodies, not the user's phrasing\n"
                "- Think: what words would the sender have written in the subject line?\n"
                "- Use email domains (from:company.com) not display names (from:Company)\n"
                "- Query 1: combine from: AND subject: operators for maximum precision\n"
                "- Query 2: single operator (from: or subject:) as fallback\n"
                "- Query 3: free text only as last resort\n"
                "- No inner quotes. Return ONLY a JSON array of 3 strings.\n\n"
                f"User intent: {intent}\n"
                f"Agent query hint: {user_query}"
            ),
        )
        raw = resp.text.strip()
        m = re.search(r"\[.*?\]", raw, re.DOTALL)
        if m:
            queries = [
                q.replace('"', "").strip() for q in json.loads(m.group()) if q.strip()
            ]
            cprint(
                f'<style fg="ansicyan">  │</style>  <style fg="ansibrightblack">⟳ rewriter:</style> <style fg="ansibrightblack">{_esc(", ".join(queries))}</style>'
            )
            return queries
    except Exception as ex:
        cprint(
            f'<style fg="ansicyan">  │</style>  <style fg="ansiyellow">⟳ rewriter: failed ({_esc(ex)}), using original</style>'
        )
    cprint(
        '<style fg="ansicyan">  │</style>  <style fg="ansibrightblack">⟳ rewriter: passthrough</style>'
    )
    return [user_query]


def _search_with_fallback(query: str, limit: int = None):
    """Try rewritten query variants in order; return first batch with results."""
    clean = query.strip()
    if clean.upper() in _PURE_IMAP:
        candidates = [clean]
    else:
        candidates = _rewrite_queries(clean, original=config._current_user_message)
        if clean not in candidates:
            candidates.append(clean)

    for q in candidates:
        _, data = _imap_search(q)
        ids = data[0].split()
        if ids:
            return ids[-limit:] if limit else ids
    return []


# ── Tool functions ─────────────────────────────────────────────────────────────


@_catch_errors
def tool_search_emails(query: str, limit: int = None) -> str:
    """
    Search emails. Use Gmail search syntax — works like Gmail's search bar.
    Examples: from:john, is:unread newer_than:7d, has:attachment,
              category:promotions, subject:invoice, order confirmation.
              Free text works too. Do NOT quote operator values.
    Pure IMAP flags: ALL, FLAGGED, UNSEEN
    """
    ensure_connected()
    ids = _search_with_fallback(query, limit)
    if not ids:
        return "No emails found."

    headers = _batch_fetch_headers(ids)
    results = []
    for mid in ids:
        h = headers.get(mid, {})
        mid_str = mid.decode()
        entry = {
            "id": mid_str,
            "from": h.get("from", ""),
            "to": h.get("to", ""),
            "cc": h.get("cc", ""),
            "reply_to": h.get("reply_to", ""),
            "subject": h.get("subject", ""),
            "date": h.get("date", ""),
            "message_id": h.get("message_id", ""),
            "in_reply_to": h.get("in_reply_to", ""),
            "references": h.get("references", ""),
            "content_type": h.get("content_type", ""),
            "labels": h.get("labels", []),
            "body": "",
            "list_unsubscribe": h.get("list_unsubscribe", ""),
            "list_unsubscribe_post": h.get("list_unsubscribe_post", ""),
            "thread_id": h.get("thread_id", ""),
            "folder": '"[Gmail]/All Mail"',
        }
        config.session_emails[mid_str] = entry
        results.append(entry)

    summary = f"Found {len(results)} email(s):\n"
    for i, e in enumerate(results, 1):
        attachment = (
            " | Has-Attachment:True" if e["content_type"] == "multipart/mixed" else ""
        )
        summary += (
            f"\n[{i}] ID:{e['id']} | From:{_clean_field(e['from'])} | "
            f"Subject:{_clean_field(e['subject'])} | Date:{e['date']} | "
            f"Labels:{e['labels']} | "
            f"Has-Unsubscribe-Header:{bool(e['list_unsubscribe'])}"
            f"{attachment}"
        )
    return summary


@_catch_errors
def tool_search_folder(folder: str, query: str = "", limit: int = None) -> str:
    """Search within a specific Gmail folder (spam, trash, sent, drafts, starred, inbox)."""
    ensure_connected()
    folder_key = folder.lower().strip()
    imap_folder = _IMAP_FOLDERS.get(folder_key)
    if not imap_folder:
        return f"Unknown folder '{folder}'. Valid: {', '.join(_IMAP_FOLDERS)}"

    config.mail.select(imap_folder)
    try:
        if query.strip():
            clean = query.replace('"', "").strip()
            _, data = config.mail.uid("search", None, f'X-GM-RAW "{clean}"')
        else:
            _, data = config.mail.uid("search", None, "ALL")

        ids = data[0].split()
        if not ids:
            return f"No emails found in {folder}."
        if limit:
            ids = ids[-limit:]

        headers = _batch_fetch_headers(ids)
        results = []
        for mid in ids:
            h = headers.get(mid, {})
            mid_str = mid.decode()
            entry = {
                "id": mid_str,
                "from": h.get("from", ""),
                "to": h.get("to", ""),
                "cc": h.get("cc", ""),
                "reply_to": h.get("reply_to", ""),
                "subject": h.get("subject", ""),
                "date": h.get("date", ""),
                "message_id": h.get("message_id", ""),
                "in_reply_to": h.get("in_reply_to", ""),
                "references": h.get("references", ""),
                "content_type": h.get("content_type", ""),
                "labels": h.get("labels", []),
                "body": "",
                "list_unsubscribe": h.get("list_unsubscribe", ""),
                "list_unsubscribe_post": h.get("list_unsubscribe_post", ""),
                "thread_id": h.get("thread_id", ""),
                "folder": imap_folder,
            }
            config.session_emails[mid_str] = entry
            results.append(entry)

        summary = f"Found {len(results)} email(s) in {folder}:\n"
        for i, e in enumerate(results, 1):
            attachment = (
                " | Has-Attachment:True"
                if e["content_type"] == "multipart/mixed"
                else ""
            )
            summary += (
                f"\n[{i}] ID:{e['id']} | From:{_clean_field(e['from'])} | "
                f"Subject:{_clean_field(e['subject'])} | Date:{e['date']} | "
                f"Labels:{e['labels']} | "
                f"Has-Unsubscribe-Header:{bool(e['list_unsubscribe'])}"
                f"{attachment}"
            )
        return summary
    finally:
        config.mail.select('"[Gmail]/All Mail"')


@_catch_errors
def tool_get_email_body(email_id: str) -> str:
    """Return the full body of a specific email by ID.
    HTML is already stripped to plain text. No artificial cap —
    the LLM decides whether and what to fetch based on the task.
    """
    cached = _get_entry(email_id).get("body", "")
    if cached:
        return cached
    ensure_connected()
    with _select_entry_folder(email_id):
        msg = fetch_msg(email_id)
        body = get_body(msg)
    if email_id in config.session_emails:
        config.session_emails[email_id]["body"] = body
    return body


@_catch_errors
def tool_get_thread(email_id: str) -> str:
    """Fetch the conversation thread for an email."""
    ensure_connected()
    e = _get_entry(email_id)
    thread_id = e.get("thread_id", "")
    with _select_entry_folder(email_id):
        if thread_id:
            _, data = config.mail.uid("search", None, f"X-GM-THRID {thread_id}")
        else:
            subject = re.sub(
                r"^(Re:|Fwd:)\s*", "", e.get("subject", ""), flags=re.IGNORECASE
            ).strip()
            if not subject:
                return "Cannot determine thread — no thread ID or subject available."
            _, data = config.mail.uid("search", None, f'SUBJECT "{subject}"')
        ids = data[0].split()
        thread = []
        for mid in ids:
            msg = fetch_msg(mid)
            thread.append(
                f"From: {msg['From']} | Date: {msg['Date']}\n{get_body(msg)[:1500]}\n---"
            )
    return f"Thread ({len(thread)} messages):\n\n" + "\n".join(thread)


@_catch_errors
def tool_parse_attachment(email_id: str) -> str:
    """Extract text from PDF or image attachments in an email."""
    ensure_connected()
    with _select_entry_folder(email_id):
        msg = fetch_msg(email_id)
    results = []
    for part in msg.walk():
        ct = part.get_content_type()
        filename = part.get_filename()
        if not filename:
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue

        if ct == "application/pdf":
            try:
                import pypdf
                import io

                reader = pypdf.PdfReader(io.BytesIO(payload))
                text = "\n".join(p.extract_text() or "" for p in reader.pages)
                results.append(f"[PDF: {filename}]\n{_clean_email_text(text)}")
            except Exception as ex:
                results.append(f"[PDF: {filename}] parse error: {ex}")

        elif ct.startswith("image/"):
            try:
                resp = config.client.models.generate_content(
                    model=config.MODEL,
                    contents=[
                        types.Part.from_bytes(data=payload, mime_type=ct),
                        "Extract all text and key information from this image.",
                    ],
                )
                results.append(f"[Image: {filename}]\n{resp.text}")
            except Exception as ex:
                results.append(f"[Image: {filename}] parse error: {ex}")

    return "\n\n".join(results) if results else "No parseable attachments found."


@_catch_errors
def tool_trash_email(email_id: str, skip_confirm: bool = False) -> str:
    """Move an email to trash after user approval.
    Set skip_confirm=true only after the user has already given explicit bulk consent."""
    e = _get_entry(email_id)
    cprint(
        f'\n  <style fg="ansibrightred">🗑  Trash</style>  <style fg="ansiwhite">{_esc(e.get("subject", email_id))}</style>'
    )
    cprint(f'     <style fg="ansibrightblack">from  {_esc(e.get("from", "?"))}</style>')
    if skip_confirm or approve("Move to trash?"):
        ensure_connected()
        folder = e.get("folder", '"[Gmail]/All Mail"')
        config.mail.select(folder)
        config.mail.uid("copy", email_id.encode(), '"[Gmail]/Trash"')
        config.mail.uid("store", email_id.encode(), "+FLAGS", "\\Deleted")
        config.mail.expunge()
        config.mail.select('"[Gmail]/All Mail"')
        return "Moved to trash."
    return "Skipped."


@_catch_errors
def tool_apply_label(email_id: str, label: str) -> str:
    """Apply a Gmail label to an email."""
    e = _get_entry(email_id)
    cprint(
        f'\n  <style fg="ansicyan">🏷  Label</style>  <style fg="ansiwhite">{_esc(e.get("subject", email_id))}</style>'
    )
    cprint(
        f'     <style fg="ansibrightblack">label  </style><style fg="ansibrightyellow">{_esc(label)}</style>'
    )
    if approve("Apply label?"):
        ensure_connected()
        with _select_entry_folder(email_id):
            config.mail.uid("store", email_id.encode(), "+X-GM-LABELS", label)
        return f"Label '{label}' applied."
    return "Skipped."


def _set_seen_flag(email_id: str, read: bool) -> str:
    ensure_connected()
    op = "+FLAGS" if read else "-FLAGS"
    with _select_entry_folder(email_id):
        config.mail.uid("store", email_id.encode(), op, "\\Seen")
    return "Marked as read." if read else "Marked as unread."


@_catch_errors
def tool_mark_read(email_id: str) -> str:
    """Mark an email as read."""
    return _set_seen_flag(email_id, read=True)


@_catch_errors
def tool_mark_unread(email_id: str) -> str:
    """Mark an email as unread."""
    return _set_seen_flag(email_id, read=False)


@_catch_errors
def tool_draft_reply(email_id: str, draft_body: str) -> str:
    """Show a draft reply and send after user approval."""
    e = _get_entry(email_id)
    to = e.get("reply_to") or e.get("from", "")
    subject = e.get("subject", "")
    reply_subject = (
        subject if re.match(r"re:", subject, re.IGNORECASE) else f"Re: {subject}"
    )
    cprint('\n  <style fg="ansibrightyellow">✉  Draft Reply</style>')
    cprint(
        f'     <style fg="ansibrightblack">to      </style><style fg="ansiwhite">{_esc(to)}</style>'
    )
    cprint(
        f'     <style fg="ansibrightblack">subject </style><style fg="ansiwhite">{_esc(reply_subject)}</style>'
    )
    cprint(f'  <style fg="ansibrightblack">{"─" * _RULE_W}</style>')
    for line in draft_body.splitlines():
        cprint(f'  <style fg="ansiwhite">{_esc(line)}</style>')
    cprint(f'  <style fg="ansibrightblack">{"─" * _RULE_W}</style>')
    approved, final_body = _approve_draft(draft_body)
    if approved:
        _send_smtp(
            to,
            reply_subject,
            final_body,
            in_reply_to=e.get("message_id", ""),
            references=e.get("references", ""),
        )
        return "Reply sent."
    return "Reply cancelled."


@_catch_errors
def tool_http_request(
    url: str, method: str = "GET", headers: dict = None, body: dict = None
) -> str:
    """
    Make an HTTP GET or POST request.
    Used for unsubscribing per RFC 8058:
      - If List-Unsubscribe-Post header present → POST with {'List-Unsubscribe': 'One-Click'}
      - If only List-Unsubscribe URL → GET
      - If no headers → extract link from body → GET
    Also usable for any other web request.
    """
    cprint(
        f'\n  <style fg="ansicyan">🌐  HTTP {_esc(method.upper())}</style>  <style fg="ansibrightblack">{_esc(url[:70])}</style>'
    )
    if body:
        cprint(
            f'     <style fg="ansibrightblack">body  {_esc(json.dumps(body)[:60])}</style>'
        )
    if approve(f"Execute {method.upper()} request?"):
        h = headers or {}
        h.setdefault("User-Agent", "Mozilla/5.0")
        if method.upper() == "POST":
            r = requests.post(
                url,
                data=body or {"List-Unsubscribe": "One-Click"},
                headers=h,
                timeout=15,
                allow_redirects=True,
            )
        else:
            r = requests.get(url, headers=h, timeout=15, allow_redirects=True)
        return (
            f"Status {r.status_code}. "
            f"{'Success.' if r.status_code == 200 else 'May need manual check.'}"
        )
    return "Skipped."


@_catch_errors
def tool_create_calendar_event(
    title: str,
    date: str,
    time: str,
    duration_minutes: int = 60,
    description: str = "",
    location: str = "",
) -> str:
    """
    Open Google Calendar in browser with pre-filled event. Zero API setup needed.
    date: YYYY-MM-DD  |  time: HH:MM (24h format)
    """
    cprint(
        f'\n  <style fg="ansibrightgreen">📅  Calendar Event</style>  <style fg="ansiwhite">{_esc(title)}</style>'
    )
    cprint(
        f'     <style fg="ansibrightblack">when  </style><style fg="ansiwhite">{date}  {time}  ({duration_minutes} min)</style>'
    )
    if location:
        cprint(
            f'     <style fg="ansibrightblack">where </style><style fg="ansiwhite">{_esc(location)}</style>'
        )
    if approve("Open Google Calendar to create this event?"):
        start_dt = f"{date.replace('-', '')}T{time.replace(':', '')}00"
        h, m = int(time[:2]), int(time[3:5])
        total = h * 60 + m + duration_minutes
        eh, em = divmod(total, 60)
        end_dt = f"{date.replace('-', '')}T{eh:02d}{em:02d}00"
        params = {
            "action": "TEMPLATE",
            "text": title,
            "dates": f"{start_dt}/{end_dt}",
            "details": description,
            "location": location,
        }
        url = "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(
            params
        )
        webbrowser.open(url)
        return "Google Calendar opened in browser. Click Save to confirm."
    return "Skipped."


@_catch_errors
def tool_suggest_new_tool(description: str, example_request: str) -> str:
    """Log a capability gap for future development."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "description": description,
        "example_request": example_request,
    }
    _append_tool_log(entry)
    return f"Logged: '{description}'. Will be addressed in a future version."


@_catch_errors
def tool_trash_emails_bulk(email_ids: list) -> str:
    """Trash multiple emails in one IMAP round trip per folder. Use after bulk user consent."""
    ensure_connected()
    by_folder: dict[str, list[bytes]] = {}
    for eid in email_ids:
        folder = config.session_emails.get(eid, {}).get("folder", '"[Gmail]/All Mail"')
        by_folder.setdefault(folder, []).append(eid.encode())

    trashed = 0
    for folder, uids in by_folder.items():
        config.mail.select(folder)
        uid_set = b",".join(uids)
        config.mail.uid("copy", uid_set, '"[Gmail]/Trash"')
        config.mail.uid("store", uid_set, "+FLAGS", "\\Deleted")
        config.mail.expunge()
        trashed += len(uids)

    config.mail.select('"[Gmail]/All Mail"')
    return f"Moved {trashed} email(s) to trash."


# ── Tool registry ──────────────────────────────────────────────────────────────

TOOLS_FN = {
    "search_emails": tool_search_emails,
    "search_folder": tool_search_folder,
    "get_email_body": tool_get_email_body,
    "get_thread": tool_get_thread,
    "parse_attachment": tool_parse_attachment,
    "trash_email": tool_trash_email,
    "trash_emails_bulk": tool_trash_emails_bulk,
    "apply_label": tool_apply_label,
    "mark_read": tool_mark_read,
    "mark_unread": tool_mark_unread,
    "draft_reply": tool_draft_reply,
    "http_request": tool_http_request,
    "create_calendar_event": tool_create_calendar_event,
    "suggest_new_tool": tool_suggest_new_tool,
}

EMAIL_ID_SCHEMA = types.Schema(
    type=types.Type.STRING, description="Email ID from search_emails result"
)
_EMAIL_ID_PARAMS = {
    "properties": {"email_id": EMAIL_ID_SCHEMA},
    "required": ["email_id"],
}

TOOL_DECLARATIONS = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="search_emails",
            description=(
                "Search emails in inbox/all mail. Excludes spam and trash. "
                "Use Gmail search syntax (preferred): "
                "'from:alice' (by name or email), "
                "'is:unread' (unread), "
                "'is:unread from:alice' (unread from alice), "
                "'newer_than:7d' (last 7 days), "
                "'newer_than:1w has:attachment' (last week with attachment), "
                "'subject:invoice', "
                "'category:promotions' (newsletters/marketing), "
                "'older_than:1y' (older than 1 year), "
                "'has:attachment filename:pdf'. "
                "Combine operators naturally. "
                "Plain IMAP fallback (no operators): 'ALL', 'FLAGGED', 'UNSEEN'. "
                "For spam/trash/sent/drafts use search_folder instead."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query": types.Schema(
                        type=types.Type.STRING,
                        description="Gmail search syntax or plain IMAP query. Do not quote operator values: write from:company not from:'company'.",
                    ),
                    "limit": types.Schema(
                        type=types.Type.INTEGER,
                        description="Max emails to return. Omit to return all results. Set to 1 for 'latest/most recent'. Set explicitly for bulk tasks.",
                    ),
                },
                required=["query"],
            ),
        ),
        types.FunctionDeclaration(
            name="search_folder",
            description=(
                "Search within a specific Gmail folder: spam, trash, sent, drafts, starred, inbox. "
                "Use this whenever the user mentions a folder by name. "
                "Examples: 'emails in spam', 'latest in trash', 'sent emails to alice', 'drafts'. "
                "Optionally filter with a query (Gmail search syntax, no in:/label: operators needed)."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "folder": types.Schema(
                        type=types.Type.STRING,
                        description="One of: spam, trash, sent, draft, starred, inbox",
                    ),
                    "query": types.Schema(
                        type=types.Type.STRING,
                        description="Optional Gmail search filter, e.g. 'from:alice' or 'subject:invoice'",
                    ),
                    "limit": types.Schema(
                        type=types.Type.INTEGER,
                        description="Max emails to return. Omit to return all results. Set to 1 for 'latest/most recent'. Set explicitly for bulk tasks.",
                    ),
                },
                required=["folder"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_email_body",
            description="Get full body of a specific email by ID. Use when you need to read the content in detail.",
            parameters=types.Schema(type=types.Type.OBJECT, **_EMAIL_ID_PARAMS),
        ),
        types.FunctionDeclaration(
            name="get_thread",
            description="Fetch full conversation thread for an email. Use when email is a reply or user wants full context.",
            parameters=types.Schema(type=types.Type.OBJECT, **_EMAIL_ID_PARAMS),
        ),
        types.FunctionDeclaration(
            name="parse_attachment",
            description="Extract text from PDF or image attachments. Use for invoices, contracts, or images where the data is in the attachment file.",
            parameters=types.Schema(type=types.Type.OBJECT, **_EMAIL_ID_PARAMS),
        ),
        types.FunctionDeclaration(
            name="trash_email",
            description="Move a single email to trash. Requires user approval unless skip_confirm=true.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "email_id": EMAIL_ID_SCHEMA,
                    "skip_confirm": types.Schema(
                        type=types.Type.BOOLEAN,
                        description="Set true only after explicit bulk user consent. Default false.",
                    ),
                },
                required=["email_id"],
            ),
        ),
        types.FunctionDeclaration(
            name="trash_emails_bulk",
            description=(
                "Trash multiple emails in one IMAP operation. "
                "Use this — not trash_email — whenever the user has confirmed a bulk deletion (e.g. said yes to 'Proceed with all N?'). "
                "Pass the complete list of email IDs in a single call."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "email_ids": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.STRING),
                        description="List of email IDs to trash",
                    ),
                },
                required=["email_ids"],
            ),
        ),
        types.FunctionDeclaration(
            name="apply_label",
            description="Apply a Gmail label. Standard: '\\\\Starred', '\\\\Important'. Or any custom label string.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "email_id": EMAIL_ID_SCHEMA,
                    "label": types.Schema(type=types.Type.STRING),
                },
                required=["email_id", "label"],
            ),
        ),
        types.FunctionDeclaration(
            name="mark_read",
            description="Mark an email as read.",
            parameters=types.Schema(type=types.Type.OBJECT, **_EMAIL_ID_PARAMS),
        ),
        types.FunctionDeclaration(
            name="mark_unread",
            description="Mark an email as unread.",
            parameters=types.Schema(type=types.Type.OBJECT, **_EMAIL_ID_PARAMS),
        ),
        types.FunctionDeclaration(
            name="draft_reply",
            description=(
                "Draft and send a reply after user approval. "
                "Write a natural, helpful reply. Use when user asks to reply "
                "or email clearly requires a response."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "email_id": EMAIL_ID_SCHEMA,
                    "draft_body": types.Schema(
                        type=types.Type.STRING, description="Full reply text"
                    ),
                },
                required=["email_id", "draft_body"],
            ),
        ),
        types.FunctionDeclaration(
            name="http_request",
            description=(
                "Make an HTTP GET or POST request. Primary use: unsubscribing per RFC 8058. "
                "Logic: "
                "1) list_unsubscribe_post header present → POST to list_unsubscribe URL "
                "   with body {'List-Unsubscribe': 'One-Click'}. "
                "2) Only list_unsubscribe URL present → GET that URL. "
                "3) No headers → extract unsubscribe link from email body → GET it. "
                "Also usable for any general HTTP request the user asks for."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "url": types.Schema(type=types.Type.STRING),
                    "method": types.Schema(
                        type=types.Type.STRING, description="GET or POST"
                    ),
                    "headers": types.Schema(
                        type=types.Type.OBJECT,
                        description="Optional HTTP headers as key-value pairs",
                    ),
                    "body": types.Schema(
                        type=types.Type.OBJECT,
                        description="Optional form data for POST as key-value pairs",
                    ),
                },
                required=["url", "method"],
            ),
        ),
        types.FunctionDeclaration(
            name="create_calendar_event",
            description="Create a Google Calendar event by opening a pre-filled browser URL. No API or credentials needed.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "title": types.Schema(type=types.Type.STRING),
                    "date": types.Schema(
                        type=types.Type.STRING, description="YYYY-MM-DD"
                    ),
                    "time": types.Schema(
                        type=types.Type.STRING, description="HH:MM in 24h format"
                    ),
                    "duration_minutes": types.Schema(
                        type=types.Type.INTEGER,
                        description="Duration in minutes, default 60",
                    ),
                    "description": types.Schema(type=types.Type.STRING),
                    "location": types.Schema(type=types.Type.STRING),
                },
                required=["title", "date", "time"],
            ),
        ),
        types.FunctionDeclaration(
            name="suggest_new_tool",
            description="Call when no existing tool can handle the user's request. Logs the capability gap for future development.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "description": types.Schema(
                        type=types.Type.STRING, description="What capability is missing"
                    ),
                    "example_request": types.Schema(
                        type=types.Type.STRING,
                        description="User's original request verbatim",
                    ),
                },
                required=["description", "example_request"],
            ),
        ),
    ]
)
