import gradio as gr
import config
from main import run_agent, init_chat
from tools import connect_imap
import os

_initialized = False

# ── Styles ────────────────────────────────────────────────────────────────────

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500&display=swap');

:root {
  --bg:        #0b0b0b;
  --surface:   #111111;
  --surface2:  #161616;
  --border2:   #282828;
  --amber:     #e8a020;
  --amber-dim: #c48018;
  --amber-lo:  rgba(232,160,32,0.09);
  --amber-mid: rgba(232,160,32,0.22);
  --text:      #d4ccc0;
  --muted:     #5a5349;
  --success:   #4ade80;
  --error:     #f87171;
  --mono: 'IBM Plex Mono','JetBrains Mono','Fira Code',monospace;
  --sans: 'IBM Plex Sans',system-ui,sans-serif;
  --r: 8px;
}

*, *::before, *::after { box-sizing: border-box; }
html, body { background: var(--bg) !important; margin: 0; padding: 0; }
footer, .built-with { display: none !important; }

/* ── Container ── */
.gradio-container {
  background: var(--bg) !important;
  font-family: var(--sans) !important;
  width: 100% !important;
  max-width: 900px !important;
  margin: 0 auto !important;
  padding: clamp(0.75rem, 3vw, 1.5rem) clamp(0.75rem, 3vw, 1.5rem) 1.5rem !important;
  min-height: 100vh !important;
}

/* ── Header ── */
#ga-header p {
  font-family: var(--mono) !important;
  font-size: clamp(0.78rem, 2vw, 0.92rem) !important;
  font-weight: 600 !important;
  letter-spacing: 0.13em !important;
  text-transform: uppercase !important;
  color: var(--amber) !important;
  margin: 0 !important;
}
#ga-byline p {
  font-family: var(--mono) !important;
  font-size: clamp(0.65rem, 1.5vw, 0.74rem) !important;
  color: var(--muted) !important;
  margin: 0.15rem 0 clamp(0.75rem, 3vh, 1.5rem) !important;
}

/* ── Setup card ──
   Gradio hides form children with .hidden but keeps the gr.Group wrapper in DOM.
   Styling the group directly shows an empty bordered rectangle when connected.
   Fix: apply card appearance only on the .styler when its .form is NOT hidden. */
#setup-panel,
#setup-panel #setup-panel {
  background: transparent !important;
  border: none !important;
  padding: 0 !important;
  box-shadow: none !important;
}
/* Card appears only when form is visible (:has is supported in all modern browsers) */
#setup-panel .styler:has(.form:not(.hidden)) {
  background: var(--surface) !important;
  border: 1px solid var(--border2) !important;
  border-radius: var(--r) !important;
  padding: clamp(1rem, 4vw, 1.75rem) !important;
}
/* Flex column layout with proper gap, overriding --layout-gap:1px inline variable */
#setup-panel .styler,
#setup-panel .form {
  gap: 0.85rem !important;
  display: flex !important;
  flex-direction: column !important;
}

.block label > span, .label-wrap > span {
  font-family: var(--mono) !important;
  font-size: 0.67rem !important;
  letter-spacing: 0.1em !important;
  text-transform: uppercase !important;
  color: var(--muted) !important;
  display: block !important;
  margin-bottom: 0.25rem !important;
}
.block .info {
  font-family: var(--mono) !important;
  font-size: 0.68rem !important;
  color: var(--muted) !important;
  margin-top: 0.2rem !important;
  word-break: break-word !important;
}

/* inputs */
.block input[type="text"],
.block input[type="password"],
.block textarea {
  background: var(--bg) !important;
  border: 1px solid var(--border2) !important;
  border-radius: 6px !important;
  color: var(--text) !important;
  font-family: var(--mono) !important;
  font-size: clamp(0.8rem, 2vw, 0.875rem) !important;
  padding: 0.6rem 0.85rem !important;
  width: 100% !important;
  transition: border-color 0.18s, box-shadow 0.18s !important;
}
.block input:focus, .block textarea:focus {
  border-color: var(--amber-dim) !important;
  box-shadow: 0 0 0 3px var(--amber-lo) !important;
  outline: none !important;
}
.block input::placeholder, .block textarea::placeholder { color: var(--border2) !important; }

/* ── Buttons ── */
button.primary {
  background: var(--amber) !important;
  color: #0b0b0b !important;
  font-family: var(--mono) !important;
  font-size: 0.75rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.08em !important;
  text-transform: uppercase !important;
  border: none !important;
  border-radius: 6px !important;
  min-height: 44px !important;
  cursor: pointer !important;
  transition: background 0.15s, transform 0.1s, opacity 0.15s !important;
}
button.primary:hover  { background: var(--amber-dim) !important; }
button.primary:active { transform: scale(0.98) !important; }
button.primary[disabled], button.primary.generating, button.primary.pending {
  opacity: 0.65 !important; cursor: wait !important; background: var(--amber-dim) !important;
}

button.secondary {
  background: transparent !important;
  border: 1px solid var(--border2) !important;
  color: var(--muted) !important;
  font-family: var(--mono) !important;
  font-size: 0.72rem !important;
  border-radius: 6px !important;
  min-height: 44px !important;
  padding: 0.6rem 1rem !important;
  cursor: pointer !important;
  white-space: nowrap !important;
  transition: border-color 0.15s, color 0.15s !important;
}
button.secondary:hover { border-color: var(--muted) !important; color: var(--text) !important; }

/* ── Setup status (gr.HTML — full control over success/error/connecting states) ── */
#setup-status { min-height: 0 !important; }
#setup-status .st-connecting,
#setup-status .st-ok,
#setup-status .st-err {
  font-family: var(--mono);
  font-size: 0.78rem;
  margin: 0.75rem 0 0;
  padding: 0.5rem 0.8rem;
  border-radius: 5px;
  word-break: break-word;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
#setup-status .st-connecting {
  color: var(--amber);
  background: rgba(232,160,32,0.08);
  border: 1px solid rgba(232,160,32,0.25);
  animation: ga-blink 1.1s ease-in-out infinite;
}
@keyframes ga-blink { 0%,100% { opacity: 1; } 50% { opacity: 0.45; } }
#setup-status .st-ok {
  color: var(--success);
  background: rgba(74,222,128,0.07);
  border: 1px solid rgba(74,222,128,0.2);
}
#setup-status .st-err {
  color: var(--error);
  background: rgba(248,113,113,0.07);
  border: 1px solid rgba(248,113,113,0.2);
}

/* ── Chat panel: strip the Group itself AND all inner .block wrappers ── */
#chat-panel,
#chat-panel .block {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  gap: 0.5rem !important;
}

/* ── Connection badge ── */
#conn-badge p {
  font-family: var(--mono) !important;
  font-size: clamp(0.6rem, 1.5vw, 0.67rem) !important;
  letter-spacing: 0.07em !important;
  color: var(--success) !important;
  margin: 0 0 0.5rem !important;
  word-break: break-all !important;
}
/* prevent Gradio Markdown rendering email as mailto link */
#conn-badge a {
  color: var(--success) !important;
  text-decoration: none !important;
  pointer-events: none !important;
  cursor: default !important;
}

/* ── Chatbot wrapper — JS sets height; ID selector wins over .block reset above ── */
#chatbot-wrap {
  border: 1px solid var(--border2) !important;
  border-radius: var(--r) !important;
  overflow: hidden !important;
  background: var(--bg) !important;
  padding: 0 !important;
}
/* Force every inner div dark — Base theme injects a gray surface color */
#chatbot-wrap > div,
#chatbot-wrap .chatbot,
#chatbot-wrap [class*="wrap"],
#chatbot-wrap [class*="scroll"],
#chatbot-wrap [class*="messages"] {
  background: var(--bg) !important;
}
#chatbot-wrap * {
  scrollbar-width: thin !important;
  scrollbar-color: var(--border2) transparent !important;
}
/* Toolbar icon buttons at top of chatbot — hidden via .ga-toolbar-btn added by JS */
.ga-toolbar-btn { display: none !important; }

/* ── Messages (panel layout) ── */
.message-wrap { padding: 0.75rem !important; gap: 0.4rem !important; }
.message-row.user-row { justify-content: flex-end !important; }
.message-row.bot-row  { justify-content: flex-start !important; }

/* Reset Gradio's own bubble-border wrapper (prevents double-border) */
.message-bubble-border {
  background: transparent !important;
  border: none !important;
  border-radius: 0 !important;
  padding: 0 !important;
  box-shadow: none !important;
  max-width: none !important;
}

/* JS-stamped bubble classes — reliable regardless of Gradio's internal names */
.ga-bubble-user {
  background: var(--amber-lo) !important;
  border: 1px solid var(--amber-mid) !important;
  border-radius: 14px 14px 3px 14px !important;
  color: var(--text) !important;
  padding: 0.55rem 0.85rem !important;
  max-width: min(500px, 84%) !important;
  width: fit-content !important;
  height: auto !important;
  min-height: 0 !important;
  font-size: 0.9rem !important;
  line-height: 1.6 !important;
  margin-left: auto !important;
}
.ga-bubble-bot {
  background: var(--surface) !important;
  border: 1px solid var(--border2) !important;
  border-radius: 3px 14px 14px 14px !important;
  color: var(--text) !important;
  padding: 0.55rem 0.85rem !important;
  max-width: min(620px, 92%) !important;
  width: fit-content !important;
  height: auto !important;
  min-height: 0 !important;
  font-size: 0.9rem !important;
  line-height: 1.6 !important;
}

/* User bubble */
.message.user {
  background: var(--amber-lo) !important;
  border: 1px solid var(--amber-mid) !important;
  border-radius: 14px 14px 3px 14px !important;
  color: var(--text) !important;
  padding: 0.55rem 0.85rem !important;
  max-width: min(500px, 84%) !important;
  width: fit-content !important;
  height: auto !important;
  min-height: 0 !important;
  font-size: 0.9rem !important;
  line-height: 1.6 !important;
}

/* Bot bubble */
.message.bot {
  background: var(--surface) !important;
  border: 1px solid var(--border2) !important;
  border-radius: 3px 14px 14px 14px !important;
  color: var(--text) !important;
  padding: 0.55rem 0.85rem !important;
  max-width: min(620px, 92%) !important;
  width: fit-content !important;
  height: auto !important;
  min-height: 0 !important;
  font-size: 0.9rem !important;
  line-height: 1.6 !important;
}

/* prose */
.message p, .message li { font-family: var(--sans) !important; margin: 0.25em 0 !important; }
.message code {
  font-family: var(--mono) !important;
  background: var(--surface2) !important;
  border-radius: 3px !important;
  font-size: 0.82em !important;
  padding: 0.1em 0.3em !important;
}
.message pre {
  font-family: var(--mono) !important;
  background: var(--surface2) !important;
  border-radius: 5px !important;
  font-size: 0.82em !important;
  padding: 0.6rem !important;
  overflow-x: auto !important;
}

/* hide chatbot action toolbar (share / delete / copy icons) */
.message-buttons, .copy-btn, .share-btn,
[data-testid="chatbot-copy-button"],
[data-testid="chatbot-share-button"],
[data-testid="chatbot-delete-button"] { display: none !important; }

/* ── Thinking indicator ── */
#thinking-wrap {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 0.5rem 0.85rem;
  background: var(--surface);
  border: 1px solid var(--border2);
  border-radius: var(--r);
  margin: 0.25rem 0;
}
.ga-dots { display: flex; gap: 5px; align-items: center; }
.ga-dots span {
  display: block; width: 6px; height: 6px; border-radius: 50%;
  background: var(--amber); opacity: 0.25;
  animation: ga-bounce 1.4s ease-in-out infinite;
}
.ga-dots span:nth-child(2) { animation-delay: 0.18s; }
.ga-dots span:nth-child(3) { animation-delay: 0.36s; }
@keyframes ga-bounce {
  0%,80%,100% { opacity: 0.25; transform: scale(0.75); }
  40%          { opacity: 1;    transform: scale(1); }
}
.ga-thinking-label {
  font-family: var(--mono); font-size: 0.7rem;
  letter-spacing: 0.06em; color: var(--muted); white-space: nowrap;
}

/* ── Message input ── */
#msg-input textarea {
  background: var(--surface) !important;
  border: 1px solid var(--border2) !important;
  border-radius: var(--r) !important;
  color: var(--text) !important;
  font-family: var(--sans) !important;
  font-size: clamp(0.875rem, 2vw, 0.95rem) !important;
  padding: 0.75rem 1rem !important;
  resize: none !important;
  min-height: 50px !important;
  width: 100% !important;
  transition: border-color 0.18s, box-shadow 0.18s !important;
}
#msg-input textarea:focus {
  border-color: var(--amber-dim) !important;
  box-shadow: 0 0 0 3px var(--amber-lo) !important;
  outline: none !important;
}
#msg-input textarea::placeholder { color: var(--muted) !important; }

/* ── Send / Clear row ── */
#send-row {
  display: flex !important;
  gap: 0.5rem !important;
  align-items: stretch !important;
  overflow: visible !important;
}
#send-row > * { min-width: 0 !important; }
#send-row button.primary   { flex: 1 1 auto !important; width: auto !important; }
#send-row button.secondary { flex: 0 0 auto !important; width: auto !important; }

/* ── Keyboard hint ── */
#kb-hint p {
  font-family: var(--mono) !important;
  font-size: 0.64rem !important;
  color: var(--border2) !important;
  margin: 0.2rem 0 0 !important;
  text-align: right !important;
}

/* ── Examples ── */
.examples-holder { margin-top: 0.5rem !important; }
.examples-holder table {
  border-spacing: 4px !important;
  border-collapse: separate !important;
  width: 100% !important;
}
.examples-holder table td {
  background: var(--surface) !important;
  border: 1px solid var(--border2) !important;
  border-radius: 5px !important;
  color: var(--muted) !important;
  font-family: var(--mono) !important;
  font-size: clamp(0.64rem, 1.5vw, 0.71rem) !important;
  padding: 0.32rem 0.65rem !important;
  cursor: pointer !important;
  white-space: normal !important;
  word-break: break-word !important;
  transition: border-color 0.15s, color 0.15s !important;
}
.examples-holder table td:hover {
  border-color: var(--amber-dim) !important;
  color: var(--amber) !important;
}

/* ── Mobile ── */
@media (max-width: 480px) {
  #setup-panel { padding: 1rem !important; }
  #kb-hint { display: none !important; }
}
"""

# ── JavaScript ─────────────────────────────────────────────────────────────────

CUSTOM_JS = """
() => {
  /* 1. Connect button loading-text feedback */
  function hookConnectBtn() {
    const btn = document.querySelector('#connect-btn button');
    if (!btn || btn._gaHooked) return;
    btn._gaHooked = true;
    btn.addEventListener('click', () => {
      const saved = btn.innerHTML;
      btn.innerHTML = '&#9711;&nbsp;&nbsp;Connecting&hellip;';
      const mo = new MutationObserver(() => {
        if (!btn.hasAttribute('disabled') && !btn.classList.contains('pending')) {
          mo.disconnect();
          btn._gaHooked = false;
          btn.innerHTML = saved;
        }
      });
      mo.observe(btn, { attributes: true, attributeFilter: ['disabled', 'class'] });
    });
  }

  /* 2. Resize chatbot to fill remaining viewport */
  function fitChatbot() {
    const wrap = document.querySelector('#chatbot-wrap');
    if (!wrap) return;
    const top = wrap.getBoundingClientRect().top + window.scrollY;
    const reserve = 200;
    const h = Math.max(280, window.innerHeight - top - reserve);
    wrap.style.height = h + 'px';
    const inner = wrap.querySelector('.chatbot, [class*="chatbot"]');
    if (inner) inner.style.height = h + 'px';
  }

  /* 3. Hide toolbar icon-buttons inside chatbot (share/delete/copy) */
  function hideToolbar() {
    const wrap = document.querySelector('#chatbot-wrap');
    if (!wrap) return;
    wrap.querySelectorAll('button').forEach(btn => {
      if (btn.querySelector('svg') || btn.querySelector('i')) {
        btn.classList.add('ga-toolbar-btn');
      }
    });
  }

  /* 4. Stamp custom classes on message rows so CSS can reliably style them */
  function stampMessages() {
    document.querySelectorAll('#chatbot-wrap .message-row, #chatbot-wrap [class*="message-row"]').forEach(row => {
      const isUser = row.classList.contains('user-row') || /user/i.test(row.className);
      // The immediate bubble child: first div inside the row
      const bubble = row.querySelector('div');
      if (!bubble) return;
      if (isUser) {
        bubble.classList.add('ga-bubble-user');
      } else {
        bubble.classList.add('ga-bubble-bot');
      }
    });
  }

  window.addEventListener('resize', fitChatbot);
  const domObs = new MutationObserver(() => {
    hookConnectBtn();
    fitChatbot();
    hideToolbar();
    stampMessages();
  });
  domObs.observe(document.body, { childList: true, subtree: true });
  hookConnectBtn();
  setTimeout(fitChatbot, 200);
  setTimeout(fitChatbot, 600);
  setTimeout(fitChatbot, 1400);
}
"""

THINKING_HTML = """
<div id="thinking-wrap">
  <div class="ga-dots"><span></span><span></span><span></span></div>
  <span class="ga-thinking-label">agent is thinking</span>
</div>
"""

# ── Logic ──────────────────────────────────────────────────────────────────────

def initialize():
    global _initialized
    missing = config.validate_env()
    if missing:
        return False, missing
    try:
        connect_imap()
        init_chat()
        _initialized = True
        return True, []
    except Exception as e:
        return False, [str(e)]


def save_credentials(email, app_password, gemini_key, model):
    """Generator — yields connecting state immediately, then result."""
    if email:
        config.EMAIL = email;  os.environ["EMAIL"] = email
    if app_password:
        config.APP_PASSWORD = app_password;  os.environ["APP_PASSWORD"] = app_password
    if gemini_key:
        config.GEMINI_KEY = gemini_key;  os.environ["GEMINI_KEY"] = gemini_key
    if model:
        config.MODEL = model;  os.environ["MODEL"] = model

    # Immediate visual feedback before blocking IMAP call
    yield (
        gr.update(),
        gr.update(),
        '<p class="st-connecting">⟳ &nbsp;Connecting to Gmail…</p>',
    )

    success, result = initialize()
    if success:
        yield (
            gr.update(visible=False),
            gr.update(visible=True),
            '<p class="st-ok">✓ &nbsp;Connected — ready to chat.</p>',
        )
    else:
        yield (
            gr.update(visible=True),
            gr.update(visible=False),
            f'<p class="st-err">✗ &nbsp;{", ".join(result)}</p>',
        )


async def chat(message, history):
    global _initialized
    history = history or []

    if not message or not message.strip():
        yield history, "", gr.update(visible=False)
        return

    if not _initialized:
        history.append({
            "role": "assistant",
            "content": "Setup required — please fill in your credentials above.",
        })
        yield history, "", gr.update(visible=False)
        return

    try:
        history.append({"role": "user", "content": message})
        yield history, "", gr.update(visible=True)

        response = await run_agent(message)

        history.append({"role": "assistant", "content": response})
        yield history, "", gr.update(visible=False)
    except Exception as e:
        history.append({"role": "assistant", "content": f"Error: {str(e)}"})
        yield history, "", gr.update(visible=False)


# ── Build UI ───────────────────────────────────────────────────────────────────

success, _ = initialize()

with gr.Blocks(title="Gmail Agent") as demo:

    gr.Markdown("◈  GMAIL AGENT", elem_id="ga-header")
    gr.Markdown("natural language interface for your inbox", elem_id="ga-byline")

    # ── Setup panel ────────────────────────────────────────────────────────────
    with gr.Group(visible=not success, elem_id="setup-panel") as setup_panel:
        email_input = gr.Textbox(
            label="Gmail Address",
            placeholder="you@gmail.com",
            info="The Gmail account you want to connect",
        )
        app_password_input = gr.Textbox(
            label="App Password",
            type="password",
            placeholder="xxxx xxxx xxxx xxxx",
            info="myaccount.google.com/apppasswords  ·  requires 2-step verification",
        )
        gemini_key_input = gr.Textbox(
            label="Gemini API Key",
            type="password",
            placeholder="AIza…",
            info="aistudio.google.com/apikey",
        )
        model_input = gr.Textbox(
            label="Model",
            value=config.MODEL,
            placeholder="gemma-4-31b-it",
            info="Leave as-is to use the default",
        )
        setup_btn = gr.Button("Connect", variant="primary", elem_id="connect-btn")
        # gr.HTML so we can inject class-based success/error/connecting styles
        setup_status = gr.HTML("", elem_id="setup-status")

    # ── Chat panel ─────────────────────────────────────────────────────────────
    with gr.Group(visible=success, elem_id="chat-panel") as chat_panel:

        # gr.Markdown (not gr.HTML) — CSS prevents email from becoming a mailto link
        if success:
            gr.Markdown(
                f"● connected  ·  {config.EMAIL}  ·  {config.MODEL}",
                elem_id="conn-badge",
            )

        chatbot = gr.Chatbot(
            height=450,
            layout="panel",
            show_label=False,
            render_markdown=True,
            elem_id="chatbot-wrap",
        )

        thinking_indicator = gr.HTML(THINKING_HTML, visible=False)

        msg = gr.Textbox(
            show_label=False,
            placeholder="Ask about your emails…",
            lines=1,
            max_lines=4,
            elem_id="msg-input",
        )

        with gr.Row(elem_id="send-row"):
            submit_btn = gr.Button("Send", variant="primary", scale=4)
            clear_btn  = gr.Button("Clear", variant="secondary", scale=1)

        gr.Markdown("↵ Enter to send", elem_id="kb-hint")
        '''
        gr.Examples(
            examples=[
                "Show my unread emails",
                "Summarize emails from this week",
                "Find emails with PDF attachments",
                "What did the email from Stripe say?",
                "Trash newsletters older than 30 days",
                "Reply to the last email from my boss",
            ],
            inputs=msg,
            label="Try an example",
        )
        '''
    # ── Events ─────────────────────────────────────────────────────────────────

    setup_btn.click(
        save_credentials,
        inputs=[email_input, app_password_input, gemini_key_input, model_input],
        outputs=[setup_panel, chat_panel, setup_status],
    )

    chat_outputs = [chatbot, msg, thinking_indicator]
    submit_btn.click(chat, inputs=[msg, chatbot], outputs=chat_outputs)
    msg.submit(chat, inputs=[msg, chatbot], outputs=chat_outputs)
    clear_btn.click(
        lambda: ([], gr.update(visible=False)),
        outputs=[chatbot, thinking_indicator],
    )

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        css=CUSTOM_CSS,
        js=CUSTOM_JS,
        theme=gr.themes.Base(
            primary_hue=gr.themes.colors.orange,
            neutral_hue=gr.themes.colors.neutral,
        ),
    )
