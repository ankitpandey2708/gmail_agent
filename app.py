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
  --border:    #1e1e1e;
  --border2:   #282828;
  --amber:     #e8a020;
  --amber-dim: #c48018;
  --amber-lo:  rgba(232,160,32,0.10);
  --amber-mid: rgba(232,160,32,0.20);
  --text:      #d4ccc0;
  --muted:     #5a5349;
  --success:   #4ade80;
  --error:     #f87171;
  --mono: 'IBM Plex Mono','JetBrains Mono','Fira Code',monospace;
  --sans: 'IBM Plex Sans',system-ui,sans-serif;
}

*, *::before, *::after { box-sizing: border-box; }

body { background: var(--bg) !important; }

.gradio-container {
  background: var(--bg) !important;
  font-family: var(--sans) !important;
  max-width: 820px !important;
  margin: 0 auto !important;
  padding: 2.5rem 1.25rem 5rem !important;
}

/* hide Gradio chrome */
footer, .built-with, .svelte-1gfkn6j { display: none !important; }

/* ── Header ── */
#ga-header {
  display: flex;
  align-items: baseline;
  gap: 0.6rem;
  margin-bottom: 0.3rem;
}
#ga-header h1 {
  font-family: var(--mono) !important;
  font-size: 0.9rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.14em !important;
  text-transform: uppercase !important;
  color: var(--amber) !important;
  margin: 0 !important;
}
#ga-byline p {
  font-size: 0.78rem !important;
  color: var(--muted) !important;
  font-family: var(--mono) !important;
  margin: 0 0 2rem !important;
}

/* ── Setup panel ── */
#setup-panel {
  background: var(--surface) !important;
  border: 1px solid var(--border2) !important;
  border-radius: 10px !important;
  padding: 1.75rem !important;
}

/* field labels */
.block label > span, .label-wrap > span {
  font-family: var(--mono) !important;
  font-size: 0.67rem !important;
  letter-spacing: 0.1em !important;
  text-transform: uppercase !important;
  color: var(--muted) !important;
  margin-bottom: 0.3rem !important;
  display: block !important;
}

/* field info text */
.block .info {
  font-family: var(--mono) !important;
  font-size: 0.7rem !important;
  color: var(--muted) !important;
  margin-top: 0.2rem !important;
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
  font-size: 0.84rem !important;
  padding: 0.6rem 0.85rem !important;
  transition: border-color 0.18s, box-shadow 0.18s !important;
  width: 100% !important;
}

.block input:focus,
.block textarea:focus {
  border-color: var(--amber-dim) !important;
  box-shadow: 0 0 0 3px var(--amber-lo) !important;
  outline: none !important;
}

.block input::placeholder,
.block textarea::placeholder {
  color: var(--border2) !important;
}

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
  padding: 0.65rem 1.6rem !important;
  cursor: pointer !important;
  transition: background 0.15s, transform 0.1s, opacity 0.15s !important;
}
button.primary:hover { background: var(--amber-dim) !important; }
button.primary:active { transform: scale(0.98) !important; }
button.primary[disabled],
button.primary.generating,
button.primary.pending {
  opacity: 0.65 !important;
  cursor: wait !important;
  background: var(--amber-dim) !important;
}

button.secondary {
  background: transparent !important;
  border: 1px solid var(--border2) !important;
  color: var(--muted) !important;
  font-family: var(--mono) !important;
  font-size: 0.72rem !important;
  letter-spacing: 0.04em !important;
  border-radius: 6px !important;
  padding: 0.6rem 1rem !important;
  transition: border-color 0.15s, color 0.15s !important;
  cursor: pointer !important;
}
button.secondary:hover {
  border-color: var(--muted) !important;
  color: var(--text) !important;
}

/* ── Setup status ── */
#setup-status .prose p,
#setup-status p {
  font-family: var(--mono) !important;
  font-size: 0.78rem !important;
  margin: 0.75rem 0 0 !important;
  padding: 0.55rem 0.8rem !important;
  border-radius: 5px !important;
}

/* success state — detect ✓ prefix via first char */
#setup-status .prose p:first-child {
  background: rgba(74,222,128,0.08) !important;
  border: 1px solid rgba(74,222,128,0.2) !important;
  color: var(--success) !important;
}

/* ── Chat panel ── */
#chat-panel { display: flex; flex-direction: column; gap: 0.75rem; }

/* Chatbot container */
#chatbot-wrap .chatbot {
  background: transparent !important;
  border: 1px solid var(--border2) !important;
  border-radius: 10px !important;
}

/* user bubble */
.message.user .message-bubble-border,
.user > .message {
  background: var(--amber-lo) !important;
  border: 1px solid var(--amber-mid) !important;
  border-radius: 8px 8px 2px 8px !important;
  color: var(--text) !important;
  font-size: 0.88rem !important;
}

/* bot bubble */
.message.bot .message-bubble-border,
.bot > .message {
  background: var(--surface) !important;
  border: 1px solid var(--border2) !important;
  border-radius: 2px 8px 8px 8px !important;
  color: var(--text) !important;
  font-size: 0.88rem !important;
}

/* message text */
.message p, .message li, .message pre {
  font-family: var(--sans) !important;
  line-height: 1.6 !important;
}
.message code, .message pre {
  font-family: var(--mono) !important;
  background: var(--surface2) !important;
  border-radius: 4px !important;
  font-size: 0.8em !important;
}

/* scrollbar */
.chatbot .scroll-hide {
  scrollbar-width: thin !important;
  scrollbar-color: var(--border2) transparent !important;
}

/* ── Thinking indicator ── */
#thinking-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0.55rem 0.9rem;
  background: var(--surface);
  border: 1px solid var(--border2);
  border-radius: 8px;
  width: fit-content;
}
.ga-dots {
  display: flex;
  align-items: center;
  gap: 5px;
}
.ga-dots span {
  display: block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--amber);
  opacity: 0.25;
  animation: ga-bounce 1.4s ease-in-out infinite;
}
.ga-dots span:nth-child(2) { animation-delay: 0.18s; }
.ga-dots span:nth-child(3) { animation-delay: 0.36s; }
@keyframes ga-bounce {
  0%,80%,100% { opacity: 0.25; transform: scale(0.75); }
  40%          { opacity: 1;    transform: scale(1);    }
}
.ga-thinking-label {
  font-family: var(--mono);
  font-size: 0.7rem;
  letter-spacing: 0.06em;
  color: var(--muted);
}

/* ── Message input ── */
#msg-input textarea {
  background: var(--surface) !important;
  border: 1px solid var(--border2) !important;
  border-radius: 8px !important;
  color: var(--text) !important;
  font-family: var(--sans) !important;
  font-size: 0.9rem !important;
  padding: 0.75rem 1rem !important;
  resize: none !important;
  transition: border-color 0.18s, box-shadow 0.18s !important;
  min-height: 52px !important;
}
#msg-input textarea:focus {
  border-color: var(--amber-dim) !important;
  box-shadow: 0 0 0 3px var(--amber-lo) !important;
  outline: none !important;
}
#msg-input textarea::placeholder { color: var(--muted) !important; }

/* ── Examples ── */
.examples-holder table { border-spacing: 4px !important; border-collapse: separate !important; }
.examples-holder table td {
  background: var(--surface) !important;
  border: 1px solid var(--border2) !important;
  border-radius: 5px !important;
  color: var(--muted) !important;
  font-family: var(--mono) !important;
  font-size: 0.7rem !important;
  padding: 0.32rem 0.7rem !important;
  cursor: pointer !important;
  transition: border-color 0.15s, color 0.15s !important;
  white-space: nowrap !important;
}
.examples-holder table td:hover {
  border-color: var(--amber-dim) !important;
  color: var(--amber) !important;
}

/* ── Keyboard hint ── */
#kb-hint p {
  font-family: var(--mono) !important;
  font-size: 0.67rem !important;
  color: var(--border2) !important;
  margin: 0 !important;
  text-align: right !important;
}

/* ── Connection badge (in chat header) ── */
#conn-badge p {
  font-family: var(--mono) !important;
  font-size: 0.67rem !important;
  letter-spacing: 0.07em !important;
  color: var(--success) !important;
  margin: 0 0 0.5rem !important;
}
"""

# ── JavaScript ─────────────────────────────────────────────────────────────────

CUSTOM_JS = """
() => {
  /* Give Connect button a loading-text state on click, reset when re-enabled */
  function hookConnectBtn() {
    const btn = document.querySelector('#connect-btn button');
    if (!btn || btn._gaHooked) return;
    btn._gaHooked = true;

    btn.addEventListener('click', () => {
      const saved = btn.innerHTML;
      btn.innerHTML = '&#9711;&nbsp;&nbsp;Connecting&hellip;';

      /* Watch for Gradio re-enabling the button (means handler finished) */
      const mo = new MutationObserver(() => {
        if (!btn.hasAttribute('disabled') && !btn.classList.contains('pending')) {
          mo.disconnect();
          btn._gaHooked = false;
          btn.innerHTML = saved;   /* restore only on failure; success hides panel */
        }
      });
      mo.observe(btn, { attributes: true, attributeFilter: ['disabled', 'class'] });
    });
  }

  const pageObs = new MutationObserver(hookConnectBtn);
  pageObs.observe(document.body, { childList: true, subtree: true });
  hookConnectBtn();
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
    if email:
        config.EMAIL = email
        os.environ["EMAIL"] = email
    if app_password:
        config.APP_PASSWORD = app_password
        os.environ["APP_PASSWORD"] = app_password
    if gemini_key:
        config.GEMINI_KEY = gemini_key
        os.environ["GEMINI_KEY"] = gemini_key
    if model:
        config.MODEL = model
        os.environ["MODEL"] = model

    success, result = initialize()
    if success:
        return (
            gr.update(visible=False),
            gr.update(visible=True),
            "✓ Connected — ready to chat.",
        )
    else:
        return (
            gr.update(visible=True),
            gr.update(visible=False),
            f"✗ {', '.join(result)}",
        )


def chat(message, history):
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
        yield history, "", gr.update(visible=True)   # show thinking indicator

        response = run_agent(message)

        history.append({"role": "assistant", "content": response})
        yield history, "", gr.update(visible=False)  # hide thinking indicator
    except Exception as e:
        history.append({"role": "assistant", "content": f"Error: {str(e)}"})
        yield history, "", gr.update(visible=False)


# ── Build UI ───────────────────────────────────────────────────────────────────

success, _ = initialize()

with gr.Blocks(
    title="Gmail Agent",
    css=CUSTOM_CSS,
    js=CUSTOM_JS,
    theme=gr.themes.Base(
        primary_hue=gr.themes.colors.orange,
        neutral_hue=gr.themes.colors.neutral,
    ),
) as demo:

    # Header
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
        setup_status = gr.Markdown("", elem_id="setup-status")

    # ── Chat panel ─────────────────────────────────────────────────────────────
    with gr.Group(visible=success, elem_id="chat-panel") as chat_panel:

        if success:
            gr.Markdown(
                f"● connected  ·  {config.EMAIL}  ·  {config.MODEL}",
                elem_id="conn-badge",
            )

        chatbot = gr.Chatbot(
            height=460,
            type="messages",
            show_label=False,
            bubble_full_width=False,
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

        with gr.Row():
            submit_btn = gr.Button("Send", variant="primary", scale=1)
            clear_btn = gr.Button("Clear", variant="secondary", scale=0)

        gr.Markdown("↵ Enter to send", elem_id="kb-hint")

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
    demo.launch(server_name="0.0.0.0", server_port=7860)
