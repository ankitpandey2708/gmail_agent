import json
import re
import time
from tools import connect_imap, TOOLS_FN, TOOL_DECLARATIONS
from datetime import datetime
from google.genai import types

import os
import config
from ui import (
    cprint,
    _rule,
    _banner,
    _show_help,
    _show_status,
    _render_agent_response,
    _section_start,
    _render_tool_result,
    _render_timing_summary,
    start_ticker,
    stop_ticker,
)


def _prompt_credential(
    label: str,
    key: str,
    hints: list[str] | None = None,
    is_password: bool = False,
) -> str:
    cprint(f'\n  <style fg="ansiwhite">{label}</style>')
    for hint in hints or []:
        cprint(f'  <style fg="ansibrightblack">  › {hint}</style>')
    while True:
        prompt_text = "  › "
        if is_password:
            import getpass

            val = getpass.getpass(prompt_text).strip()
        else:
            val = input(prompt_text).strip()
        if val:
            setattr(config, key, val)
            os.environ[key] = val
            cprint('  <style fg="ansibrightgreen">  ✓ Set.</style>')
            return val
        cprint('  <style fg="ansibrightred">  ✗ Please enter a value.</style>')


def _setup_wizard():
    """Interactive setup wizard — runs when env vars are missing."""
    cprint('\n<style fg="ansibrightyellow">  ◈  <b>Setup</b></style>')
    cprint(f'<style fg="ansibrightblack">  {_rule("━")}</style>')
    cprint(
        '  <style fg="ansibrightblack">Enter your credentials to get started.</style>'
    )

    _prompt_credential(
        "Gmail Address",
        "EMAIL",
        hints=["The Gmail account you want to connect."],
    )

    _prompt_credential(
        "Gmail App Password",
        "APP_PASSWORD",
        hints=[
            "Create one at: myaccount.google.com/apppasswords",
            "Requires 2FA enabled on your Google account.",
        ],
        is_password=True,
    )

    _prompt_credential(
        "Gemini API Key",
        "GEMINI_KEY",
        hints=["Get one at: aistudio.google.com/apikey"],
        is_password=True,
    )

    cprint('\n  <style fg="ansiwhite">Model</style>')
    cprint(
        f'  <style fg="ansibrightblack">  › Press Enter for default: {config.MODEL}</style>'
    )
    model = input("  › ").strip()
    if model:
        config.MODEL = model
        os.environ["MODEL"] = model
        cprint('  <style fg="ansibrightgreen">  ✓ Set.</style>')
    else:
        cprint(f'  <style fg="ansibrightblack">  Using default: {config.MODEL}</style>')

    cprint(f'<style fg="ansibrightblack">  {_rule("━")}</style>')
    cprint(
        '  <style fg="ansibrightyellow">  ◈  Setup complete. Launching agent…</style>\n'
    )
    os.system("clear")
    os.system("cls")
    _banner()


def _check_and_setup():
    """Check env vars and run setup wizard if needed."""
    missing = config.validate_env()
    if missing:
        _setup_wizard()
        config.client = config.ensure_client()


def _build_system_prompt() -> str:
    return f"""## Identity
You are a Gmail agent for {config.EMAIL}, running in a terminal. Today is {datetime.now().strftime("%A, %d %B %Y")}.

## Behaviour
Act immediately on read tasks — search, fetch, summarise, answer. Never ask permission to look.
Ask a clarifying question only when intent is ambiguous AND the action is irreversible. One question maximum.

## Search
Always call search_emails first — you need IDs before acting.
If a query returns nothing, try a broader or domain-based variant before giving up.

## Completing tasks
For questions about email content (amounts, dates, names), chain tools until you have the answer:
search → get_email_body → extract → respond. Do not stop at finding the email.
Always try get_email_body before parse_attachment — only call parse_attachment if the answer is not in the body.
For any bulk operation affecting multiple emails: show a summary (count + senders) and ask once "Proceed with all N?" — do not begin until confirmed.

## Output
Every response that does not call a tool MUST put ALL user-facing text — including questions and confirmations — inside <answer>...</answer>. No exceptions.

## When stuck
If no tool fits the request, call suggest_new_tool and tell the user what capability was logged.
"""


def init_chat() -> None:
    """Create a fresh chat session with the system prompt and tool declarations."""
    config._chat = config.ensure_client().chats.create(
        model=config.MODEL,
        config=types.GenerateContentConfig(
            system_instruction=_build_system_prompt(),
            tools=[TOOL_DECLARATIONS],
            temperature=0,
            max_output_tokens=4096,
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.HIGH
            ),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        ),
    )


def run_agent(user_message: str) -> str:
    """
    Send a message and run the ReAct loop:
    model responds → tool calls executed → results fed back → repeat until done.
    """
    config._current_user_message = user_message
    t_total = time.perf_counter()
    llm_total = 0.0
    llm_count = 0
    tool_total = 0.0
    tool_count = 0

    def _summary():
        _render_timing_summary(
            time.perf_counter() - t_total,
            llm_total,
            llm_count,
            tool_total,
            tool_count,
        )

    t = time.perf_counter()
    response = config._chat.send_message(user_message)
    llm_total += time.perf_counter() - t
    llm_count += 1

    MAX_ITER = 12
    for _ in range(MAX_ITER):
        parts = response.candidates[0].content.parts
        tool_calls = [p for p in parts if p.function_call]
        text_parts = [
            p
            for p in parts
            if hasattr(p, "text") and p.text and not getattr(p, "thought", False)
        ]

        if not tool_calls:
            full = "\n".join(p.text.strip() for p in text_parts if p.text.strip())
            m = re.search(r"<answer>(.*?)</answer>", full, re.DOTALL)
            _summary()
            if m:
                answer = m.group(1).strip()
                return answer if answer else full
            return full if full else "No response generated. Please try rephrasing."

        function_responses = []
        for part in tool_calls:
            fn_name = part.function_call.name
            fn_args = dict(part.function_call.args)
            args_preview = json.dumps(fn_args, ensure_ascii=False)[:120]

            _section_start("⚡", fn_name, args_preview)

            t = time.perf_counter()
            result = (
                TOOLS_FN[fn_name](**fn_args)
                if fn_name in TOOLS_FN
                else f"Error: unknown tool '{fn_name}'"
            )
            elapsed = time.perf_counter() - t
            tool_total += elapsed
            tool_count += 1
            result_str = str(result)
            _render_tool_result(fn_name, result_str, elapsed)
            function_responses.append(
                types.Part.from_function_response(
                    name=fn_name, response={"result": result_str}
                )
            )

        t = time.perf_counter()
        response = config._chat.send_message(function_responses)
        llm_total += time.perf_counter() - t
        llm_count += 1

    _summary()
    return "Max iterations reached. Try a simpler request."


SLASH_COMMANDS = sorted(
    [
        ("/clear", "Reset history and cached emails"),
        ("/exit", "Exit the agent"),
        ("/help", "Show usage examples"),
        ("/quit", "Exit the agent"),
        ("/setup", "Re-run setup wizard"),
        ("/status", "Show session status"),
    ]
)


def main():
    # _banner()
    _check_and_setup()
    connect_imap()
    init_chat()

    # Load history if readline is available (Unix-like systems)
    history_file = ".gmail_agent_history"
    try:
        import readline

        try:
            readline.read_history_file(history_file)
            readline.set_history_length(1000)
        except FileNotFoundError:
            pass

        # Set up tab completion for slash commands
        def completer(text, state):
            options = [cmd[0] for cmd in SLASH_COMMANDS if cmd[0].startswith(text)]
            if state < len(options):
                return options[state]
            return None

        readline.parse_and_bind("tab: complete")
        readline.set_completer(completer)
    except ImportError:
        pass  # readline not available on Windows

    while True:
        try:
            user_input = input("\n  ❯ ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {_rule()}")
            print("  Goodbye.\n")
            break

        # Save history after each command if readline is available
        try:
            import readline

            readline.write_history_file(history_file)
        except (ImportError, Exception):
            pass

        if not user_input:
            cprint(
                '  <style fg="ansibrightblack">Type a request or <b>/help</b> to see examples.</style>'
            )
            continue
        cmd = user_input.lower()
        if cmd in ("/quit", "/exit"):
            print(f"\n  {_rule()}")
            print("  Goodbye.\n")
            break
        if cmd == "/clear":
            config.session_emails.clear()
            init_chat()
            print(f"\n  {_rule()}")
            cprint(
                '  <style fg="ansibrightyellow">◈</style>  <style fg="ansiwhite">Session cleared</style> <style fg="ansibrightblack">— history and cache reset.</style>'
            )
            print(f"  {_rule()}")
            continue
        if cmd == "/help":
            _show_help()
            continue
        if cmd == "/setup":
            _setup_wizard()
            connect_imap()
            init_chat()
            continue
        if cmd == "/status":
            _show_status()
            continue

        print()
        start_ticker(time.perf_counter())
        response_text = run_agent(user_input)
        stop_ticker()
        _render_agent_response(response_text)

    try:
        config.mail.logout()
    except Exception:
        pass


if __name__ == "__main__":
    main()
