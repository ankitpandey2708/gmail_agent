import html as _html
import sys
import threading
import time
import re

import config

_RULE_W = 54

_ticker_lock = threading.Lock()
_ticker_active = False
_ticker_stop: threading.Event | None = None


def start_ticker(start_time: float) -> None:
    global _ticker_active, _ticker_stop
    _ticker_stop = threading.Event()
    _ticker_active = True
    stop = _ticker_stop

    def _tick():
        while not stop.is_set():
            elapsed = time.perf_counter() - start_time
            with _ticker_lock:
                if _ticker_active:
                    sys.stdout.write(f"\r  \x1b[90mworking…  {elapsed:.1f}s\x1b[0m  ")
                    sys.stdout.flush()
            stop.wait(0.1)

    threading.Thread(target=_tick, daemon=True).start()


def stop_ticker() -> None:
    global _ticker_active, _ticker_stop
    with _ticker_lock:
        _ticker_active = False
        sys.stdout.write("\n")
        sys.stdout.flush()
    if _ticker_stop:
        _ticker_stop.set()
        _ticker_stop = None


def _parse_ansi(html_text: str) -> str:
    """Convert HTML-style color tags to ANSI escape codes."""
    # Color mapping
    colors = {
        "ansiwhite": "\033[37m",
        "ansibrightblack": "\033[90m",
        "ansibrightred": "\033[91m",
        "ansibrightgreen": "\033[92m",
        "ansibrightyellow": "\033[93m",
        "ansibrightblue": "\033[94m",
        "ansibrightmagenta": "\033[95m",
        "ansibrightcyan": "\033[96m",
        "ansiblack": "\033[30m",
        "ansired": "\033[31m",
        "ansigreen": "\033[32m",
        "ansiyellow": "\033[33m",
        "ansiblue": "\033[34m",
        "ansimagenta": "\033[35m",
        "ansicyan": "\033[36m",
    }
    reset = "\033[0m"
    bold = "\033[1m"

    result = html_text
    # Handle <b> tags
    result = result.replace("<b>", bold).replace("</b>", reset)
    # Handle <style> tags
    style_pattern = r"<style\s+([^>]*)>([^<]*)</style>"

    def replace_style(match):
        attrs = match.group(1)
        text = match.group(2)
        ansi = ""
        for key, value in re.findall(r'(\w+)="([^"]*)"', attrs):
            if key == "fg" and value in colors:
                ansi += colors[value]
            elif key == "bg" and value in colors:
                # Convert fg to bg by adding 10
                bg_color = colors[value].replace("[3", "[4").replace("[9", "[10")
                ansi += bg_color
        return f"{ansi}{text}{reset}"

    result = re.sub(style_pattern, replace_style, result)
    return result


def cprint(html_text: str) -> None:
    with _ticker_lock:
        if _ticker_active:
            sys.stdout.write("\r" + " " * 50 + "\r")
            sys.stdout.flush()
        print(_parse_ansi(html_text))
        sys.stdout.flush()


def colored_input(prompt_text: str) -> str:
    """Input with ANSI color support."""
    return input(_parse_ansi(prompt_text))


def _esc(text) -> str:
    return _html.escape(str(text))


def _rule(char="─", n=_RULE_W) -> str:
    return char * n


# ── Banner & sections ──────────────────────────────────────────────────────────


def _banner() -> None:
    model_tag = config.MODEL[:42] if len(config.MODEL) > 42 else config.MODEL
    cprint("")
    cprint('<style fg="ansibrightyellow">  ◈  <b>GMAIL AGENT</b></style>')
    cprint(f'<style fg="ansibrightblack">  {_rule("━")}</style>')
    cprint(f'  <style fg="ansiwhite">{_esc(config.EMAIL)}</style>')
    cprint(f'  <style fg="ansibrightblack">Model: {_esc(model_tag)}</style>')
    cprint(f'<style fg="ansibrightblack">  {_rule("━")}</style>')
    cprint(
        '  <style fg="ansibrightblack">↑↓ history  ·  type <b>/</b> for commands  ·  <b>/help</b> for examples</style>'
    )
    cprint("")


def _section_start(icon: str, title: str, args_preview: str = "") -> None:
    cprint(
        f'<style fg="ansicyan">  ┌─ {icon} {_esc(title)}</style> <style fg="ansibrightblack">─────────────────────────────────</style>'
    )
    if args_preview:
        cprint(
            f'<style fg="ansicyan">  │</style>  <style fg="ansibrightblack">{_esc(args_preview[:80])}</style>'
        )


def _fmt_time(elapsed: float) -> str:
    if elapsed < 1:
        return f"{elapsed * 1000:.0f}ms"
    return f"{elapsed:.1f}s"


def _section_ok(title: str, msg: str, elapsed: float | None = None) -> None:
    t = (
        f' <style fg="ansibrightblack">{_fmt_time(elapsed)}</style> '
        if elapsed is not None
        else ""
    )
    cprint(
        f'<style fg="ansicyan">  └─</style> <style fg="ansibrightgreen">✓</style>  <style fg="ansibrightblack">{_esc(title)}</style>{t} → <style fg="ansiwhite">{_esc(msg)}</style>'
    )


def _section_empty(title: str, elapsed: float | None = None) -> None:
    t = (
        f' <style fg="ansibrightblack">{_fmt_time(elapsed)}</style> '
        if elapsed is not None
        else ""
    )
    cprint(
        f'<style fg="ansicyan">  └─</style> <style fg="ansiyellow">○</style>  <style fg="ansibrightblack">{_esc(title)}</style>{t} → no results'
    )


def _section_err(title: str, msg: str, elapsed: float | None = None) -> None:
    t = (
        f' <style fg="ansibrightblack">{_fmt_time(elapsed)}</style> '
        if elapsed is not None
        else ""
    )
    cprint(
        f'<style fg="ansicyan">  └─</style> <style fg="ansibrightred">✗</style>  <style fg="ansibrightblack">{_esc(title)}</style>{t} → <style fg="ansibrightred">{_esc(msg[:100])}</style>'
    )


def _render_timing_summary(
    total: float, llm_total: float, llm_count: int, tool_total: float, tool_count: int
) -> None:
    parts = [
        f'<style fg="ansiwhite"><b>{_fmt_time(total)}</b></style> <style fg="ansibrightblack">total</style>',
        f'<style fg="ansibrightblack">llm</style> <style fg="ansiwhite">{_fmt_time(llm_total)}</style> <style fg="ansibrightblack">({llm_count})</style>',
    ]
    if tool_count:
        parts.append(
            f'<style fg="ansibrightblack">tools</style> <style fg="ansiwhite">{_fmt_time(tool_total)}</style> <style fg="ansibrightblack">({tool_count})</style>'
        )
    sep = '  <style fg="ansibrightblack">·</style>  '
    cprint('  <style fg="ansibrightblack">⏱</style>  ' + sep.join(parts))


def _render_agent_response(text: str) -> None:
    cprint('\n<style fg="ansibrightyellow">  ◈  <b>Agent</b></style>')
    cprint(f'<style fg="ansibrightblack">  {_rule()}</style>')
    for line in text.splitlines():
        if line.strip():
            cprint(f'  <style fg="ansiwhite">{_esc(line)}</style>')
        else:
            cprint("")
    cprint(f'<style fg="ansibrightblack">  {_rule()}</style>')


def _render_tool_result(
    fn_name: str, result_str: str, elapsed: float | None = None
) -> None:
    if result_str == "No emails found.":
        _section_empty(fn_name, elapsed)
    elif result_str.startswith("Found "):
        lines = result_str.splitlines()
        header = lines[0] if lines else result_str
        _section_ok(fn_name, header, elapsed)
        for line in lines[1:]:
            line = line.strip()
            if " | " not in line:
                continue
            idx = "?"
            if line.startswith("["):
                bracket_end = line.find("]")
                if bracket_end != -1:
                    idx = line[1:bracket_end]
                    line = line[bracket_end + 1 :].strip()
            fields = {}
            for chunk in line.split(" | "):
                if ":" in chunk:
                    k, v = chunk.split(":", 1)
                    fields[k.strip()] = v.strip()
            subj = fields.get("Subject", "")
            frm = fields.get("From", "")
            frm = frm[:36] + "…" if len(frm) > 36 else frm
            subj_display = subj[:44] + "…" if len(subj) > 44 else subj
            cprint(
                f'<style fg="ansicyan">     {_esc(idx):>2}.</style>'
                f'  <style fg="ansiwhite">{_esc(subj_display)}</style>'
                f'  <style fg="ansibrightblack">{_esc(frm)}</style>'
            )
    elif result_str.startswith("Error"):
        _section_err(fn_name, result_str, elapsed)
    else:
        _section_ok(fn_name, result_str[:80] if result_str else "done", elapsed)


# ── Approval prompts ───────────────────────────────────────────────────────────


def approve(prompt_text: str) -> bool:
    cprint(f'<style fg="ansibrightblack">  {"─" * 40}</style>')
    val = (
        colored_input(
            f'  <style fg="ansibrightyellow">⚠</style>  '
            f'<style fg="ansiwhite">{_esc(prompt_text)}</style>  '
            f'<style fg="ansibrightblack">[y/n]</style>  '
            f'<style fg="ansibrightyellow">›</style> '
        )
        .strip()
        .lower()
    )
    return val == "y"


def _approve_draft(draft_body: str) -> tuple:
    """Send / Edit / Cancel loop for draft replies. Returns (approved, final_body)."""
    body = draft_body
    while True:
        cprint(f'<style fg="ansibrightblack">  {"─" * 40}</style>')
        val = (
            colored_input(
                '  <style fg="ansibrightyellow">⚠</style>'
                '  <style fg="ansiwhite">Send</style>'
                '  <style fg="ansibrightblack">[s]</style>  '
                '  <style fg="ansiwhite">Edit</style>'
                '  <style fg="ansibrightblack">[e]</style>  '
                '  <style fg="ansiwhite">Cancel</style>'
                '  <style fg="ansibrightblack">[c]</style>'
                '  <style fg="ansibrightyellow">  ›</style> '
            )
            .strip()
            .lower()
        )

        if val == "s":
            return True, body
        if val == "c":
            return False, body
        if val == "e":
            cprint(
                '  <style fg="ansibrightblack">Type your revised reply. Enter a blank line when done.</style>'
            )
            lines = []
            while True:
                try:
                    line = colored_input('  <style fg="ansibrightblack">  ·</style> ')
                    if line == "" and lines:
                        break
                    lines.append(line)
                except (EOFError, KeyboardInterrupt):
                    break
            if lines:
                body = "\n".join(lines)
                cprint(f'  <style fg="ansibrightblack">{"─" * _RULE_W}</style>')
                for ln in body.splitlines():
                    cprint(f'  <style fg="ansiwhite">{_esc(ln)}</style>')
                cprint(f'  <style fg="ansibrightblack">{"─" * _RULE_W}</style>')


# ── Help & status ──────────────────────────────────────────────────────────────


def _show_help() -> None:
    examples = [
        (
            "Reading",
            [
                "show my unread emails",
                "summarize emails from this week",
                "what did the email from Stripe say?",
                "find emails with PDF attachments",
            ],
        ),
        (
            "Searching",
            [
                "emails from john@example.com",
                "subject: invoice last month",
                "unread from my boss",
                "newsletters older than 3 months",
            ],
        ),
        (
            "Organizing",
            [
                "trash all promotional emails older than 30 days",
                "label the invoice email as 'bills'",
                "mark all emails from GitHub as read",
            ],
        ),
        (
            "Composing",
            [
                "reply to the Stripe email saying I'll pay by Friday",
                "reply to Sarah's last message",
            ],
        ),
        (
            "Calendar",
            [
                "create a meeting Tomorrow at 3pm called 'Team Sync'",
            ],
        ),
    ]
    cprint('\n<style fg="ansibrightyellow">  ◈  Example requests</style>')
    cprint(f'<style fg="ansibrightblack">  {_rule("━")}</style>')
    for category, items in examples:
        cprint(f'\n  <style fg="ansibrightyellow">{_esc(category)}</style>')
        for item in items:
            cprint(
                f'  <style fg="ansibrightblack">  ›</style>  <style fg="ansiwhite">{_esc(item)}</style>'
            )
    cprint(f'\n<style fg="ansibrightblack">  {_rule("━")}</style>')
    cprint(
        '  <style fg="ansibrightblack">Built-in commands:  quit · clear · help · status</style>'
    )
    cprint(f'<style fg="ansibrightblack">  {_rule("━")}</style>\n')


def _show_status() -> None:
    n = len(config.session_emails)
    conn = "connected" if config.mail else "disconnected"
    conn_color = "ansibrightgreen" if config.mail else "ansibrightred"
    cprint('\n<style fg="ansibrightyellow">  ◈  Session status</style>')
    cprint(f'<style fg="ansibrightblack">  {_rule("━")}</style>')
    cprint(
        f'  <style fg="ansibrightblack">connection</style>  <style fg="{conn_color}">{conn}</style>'
    )
    cprint(
        f'  <style fg="ansibrightblack">account   </style>  <style fg="ansiwhite">{_esc(config.EMAIL)}</style>'
    )
    cprint(
        f'  <style fg="ansibrightblack">model     </style>  <style fg="ansiwhite">{_esc(config.MODEL)}</style>'
    )
    cprint(
        f'  <style fg="ansibrightblack">cached    </style>  <style fg="ansiwhite">{n} email{"s" if n != 1 else ""}</style>'
    )
    if config.session_emails:
        cprint('\n  <style fg="ansibrightblack">Emails in cache:</style>')
        for i, (_, e) in enumerate(list(config.session_emails.items())[-8:], 1):
            subj = (e.get("subject") or "(no subject)")[:48]
            frm = (e.get("from") or "")[:30]
            cprint(
                f'  <style fg="ansicyan">  {i:>2}.</style>'
                f'  <style fg="ansiwhite">{_esc(subj)}</style>'
                f'  <style fg="ansibrightblack">{_esc(frm)}</style>'
            )
    cprint(f'<style fg="ansibrightblack">  {_rule("━")}</style>\n')
