import html as _html
import re
import gradio as gr
import config
from main import run_agent, init_chat
from tools import connect_imap
from pipeline import run_pipeline, load_queues
import triage as tr
import os

_initialized = False

# ── CSS ────────────────────────────────────────────────────────────────────────

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
  --info:      #60a5fa;
  --mono: 'IBM Plex Mono','JetBrains Mono','Fira Code',monospace;
  --sans: 'IBM Plex Sans',system-ui,sans-serif;
  --r: 8px;
}

*, *::before, *::after { box-sizing: border-box; }
html, body { background: var(--bg) !important; margin: 0; padding: 0; }
footer, .built-with { display: none !important; }

.gradio-container {
  background: var(--bg) !important;
  font-family: var(--sans) !important;
  width: 100% !important;
  max-width: 1100px !important;
  margin: 0 auto !important;
  padding: clamp(0.75rem, 3vw, 1.5rem) clamp(0.75rem, 3vw, 1.5rem) 1.5rem !important;
  min-height: 100vh !important;
}

/* ── Tabs ── */
.tabs > .tab-nav {
  border-bottom: 1px solid var(--border2) !important;
  background: transparent !important;
  margin-bottom: 1.25rem !important;
}
.tabs > .tab-nav > button {
  font-family: var(--mono) !important;
  font-size: 0.72rem !important;
  letter-spacing: 0.1em !important;
  text-transform: uppercase !important;
  color: var(--muted) !important;
  background: transparent !important;
  border: none !important;
  border-bottom: 2px solid transparent !important;
  padding: 0.5rem 1rem 0.45rem !important;
  margin-bottom: -1px !important;
  cursor: pointer !important;
  transition: color 0.15s, border-color 0.15s !important;
}
.tabs > .tab-nav > button.selected {
  color: var(--amber) !important;
  border-bottom-color: var(--amber) !important;
}
.tabs > .tab-nav > button:hover:not(.selected) {
  color: var(--text) !important;
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

/* ── Setup card ── */
#setup-panel,
#setup-panel #setup-panel {
  background: transparent !important;
  border: none !important;
  padding: 0 !important;
  box-shadow: none !important;
}
#setup-panel .styler:has(.form:not(.hidden)) {
  background: var(--surface) !important;
  border: 1px solid var(--border2) !important;
  border-radius: var(--r) !important;
  padding: clamp(1rem, 4vw, 1.75rem) !important;
}
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

#chat-panel,
#chat-panel .block {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  gap: 0.5rem !important;
}

#conn-badge p {
  font-family: var(--mono) !important;
  font-size: clamp(0.6rem, 1.5vw, 0.67rem) !important;
  letter-spacing: 0.07em !important;
  color: var(--success) !important;
  margin: 0 0 0.5rem !important;
  word-break: break-all !important;
}
#conn-badge a {
  color: var(--success) !important;
  text-decoration: none !important;
  pointer-events: none !important;
  cursor: default !important;
}

#chatbot-wrap {
  border: 1px solid var(--border2) !important;
  border-radius: var(--r) !important;
  overflow: hidden !important;
  background: var(--bg) !important;
  padding: 0 !important;
}
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
.ga-toolbar-btn { display: none !important; }

.message-wrap { padding: 0.75rem !important; gap: 0.4rem !important; }
.message-row.user-row { justify-content: flex-end !important; }
.message-row.bot-row  { justify-content: flex-start !important; }

.message-bubble-border {
  background: transparent !important;
  border: none !important;
  border-radius: 0 !important;
  padding: 0 !important;
  box-shadow: none !important;
  max-width: none !important;
}

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
.message-buttons, .copy-btn, .share-btn,
[data-testid="chatbot-copy-button"],
[data-testid="chatbot-share-button"],
[data-testid="chatbot-delete-button"] { display: none !important; }

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

#send-row {
  display: flex !important;
  gap: 0.5rem !important;
  align-items: stretch !important;
  overflow: visible !important;
}
#send-row > * { min-width: 0 !important; }
#send-row button.primary   { flex: 1 1 auto !important; width: auto !important; }
#send-row button.secondary { flex: 0 0 auto !important; width: auto !important; }

#kb-hint p {
  font-family: var(--mono) !important;
  font-size: 0.64rem !important;
  color: var(--border2) !important;
  margin: 0.2rem 0 0 !important;
  text-align: right !important;
}

/* ── Triage tab ── */

/* Pipeline stats bar */
.pl-stats {
  font-family: var(--mono); font-size: 0.72rem; color: var(--muted);
  padding: 0.45rem 0.85rem; background: var(--surface);
  border: 1px solid var(--border2); border-radius: 5px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.pl-num   { color: var(--text); font-weight: 600; }
.pl-reply { color: var(--amber); font-weight: 600; }
.pl-info  { color: var(--info); }
.pl-noise { color: var(--muted); }
.pl-meta  { color: var(--border2); }
.pl-error { color: var(--error); border-color: rgba(248,113,113,0.3); }

/* Email queue */
.triage-queue {
  display: flex; flex-direction: column; gap: 3px;
  max-height: 460px; overflow-y: auto;
  scrollbar-width: thin; scrollbar-color: var(--border2) transparent;
}
.triage-card {
  background: var(--surface); border: 1px solid var(--border2);
  border-left: 3px solid transparent;
  border-radius: 6px; padding: 0.55rem 0.75rem;
  transition: border-color 0.12s, background 0.12s;
  cursor: default;
}
.triage-card.tc-selected {
  background: var(--amber-lo) !important;
  border-color: var(--amber-dim) !important;
  border-left-color: var(--amber) !important;
}
.triage-card.tc-high {
  border-left-color: var(--amber-dim);
}
.tc-header {
  display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.18rem;
}
.tc-star   { color: var(--amber); font-size: 0.8rem; flex-shrink: 0; width: 1rem; text-align: center; }
.tc-sender { font-family: var(--mono); font-size: 0.78rem; font-weight: 500; color: var(--text); flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tc-meta   { font-family: var(--mono); font-size: 0.65rem; color: var(--muted); flex-shrink: 0; }
.tc-subject { font-family: var(--sans); font-size: 0.78rem; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding-left: 1.5rem; }
.tc-reason  { font-family: var(--sans); font-size: 0.68rem; color: var(--muted); padding-left: 1.5rem; margin-top: 0.1rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.triage-empty { font-family: var(--mono); font-size: 0.72rem; color: var(--muted); padding: 2rem; text-align: center; border: 1px solid var(--border2); border-radius: 6px; background: var(--surface); }

/* Detail panel */
.triage-detail {
  background: var(--surface); border: 1px solid var(--border2);
  border-radius: 6px; padding: 0.85rem 1rem;
}
.td-pri-badge { font-family: var(--mono); font-size: 0.62rem; letter-spacing: 0.12em; font-weight: 600; margin-bottom: 0.55rem; }
.td-pri-high   { color: var(--amber); }
.td-pri-normal { color: var(--muted); }
.td-from    { font-family: var(--mono); font-size: 0.7rem; color: var(--muted); margin-bottom: 0.15rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.td-subject { font-family: var(--sans); font-size: 0.88rem; color: var(--text); font-weight: 500; line-height: 1.3; margin-bottom: 0.25rem; }
.td-meta    { font-family: var(--mono); font-size: 0.64rem; color: var(--muted); margin-bottom: 0.5rem; }
.td-reason  { font-family: var(--sans); font-size: 0.76rem; color: var(--text); background: var(--surface2); border-radius: 4px; padding: 0.4rem 0.6rem; line-height: 1.5; }
.triage-no-sel { font-family: var(--mono); font-size: 0.72rem; color: var(--muted); padding: 2rem; text-align: center; border: 1px solid var(--border2); border-radius: 6px; background: var(--surface); }

/* Draft box override */
#reply-draft textarea {
  font-family: var(--mono) !important;
  font-size: 0.78rem !important;
  line-height: 1.6 !important;
  background: var(--surface2) !important;
  border-color: var(--border2) !important;
  color: var(--text) !important;
}

/* Activity log */
.triage-activity {
  font-family: var(--mono); font-size: 0.68rem; line-height: 1.7;
  color: var(--muted); background: var(--surface);
  border: 1px solid var(--border2); border-radius: 5px;
  padding: 0.55rem 0.75rem; max-height: 130px; overflow-y: auto;
}
.ta-item { padding: 0.05rem 0; }
.ta-ok   { color: var(--success); }
.ta-warn { color: var(--amber); }
.ta-err  { color: var(--error); }
.triage-activity-empty { font-family: var(--mono); font-size: 0.68rem; color: var(--border2); padding: 0.75rem; text-align: center; }

/* Learn panel */
.learn-results {
  font-family: var(--mono); font-size: 0.75rem; color: var(--text);
  background: var(--surface); border: 1px solid var(--border2);
  border-radius: 6px; padding: 1rem; line-height: 1.6;
}
.lr-insight { color: var(--text); margin-bottom: 0.75rem; font-family: var(--sans); font-size: 0.82rem; }
.lr-rule    { background: var(--surface2); border-radius: 4px; padding: 0.3rem 0.6rem; margin: 0.2rem 0; }
.lr-pattern { color: var(--amber); }
.lr-reason  { color: var(--muted); font-size: 0.68rem; margin-left: 0.5rem; }
.lr-applied { color: var(--success); margin-top: 0.5rem; }
.lr-err     { color: var(--error); }

@media (max-width: 480px) {
  #setup-panel { padding: 1rem !important; }
  #kb-hint { display: none !important; }
}
"""

CUSTOM_JS = """
() => {
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

  function hideToolbar() {
    const wrap = document.querySelector('#chatbot-wrap');
    if (!wrap) return;
    wrap.querySelectorAll('button').forEach(btn => {
      if (btn.querySelector('svg') || btn.querySelector('i')) {
        btn.classList.add('ga-toolbar-btn');
      }
    });
  }

  function stampMessages() {
    document.querySelectorAll('#chatbot-wrap .message-row, #chatbot-wrap [class*="message-row"]').forEach(row => {
      const isUser = row.classList.contains('user-row') || /user/i.test(row.className);
      const bubble = row.querySelector('div');
      if (!bubble) return;
      if (isUser) bubble.classList.add('ga-bubble-user');
      else        bubble.classList.add('ga-bubble-bot');
    });
  }

  function scrollSelectedCard() {
    ['reply-queue', 'info-queue'].forEach(id => {
      const wrap = document.getElementById(id);
      if (!wrap) return;
      const sel = wrap.querySelector('.tc-selected');
      if (sel) sel.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    });
  }

  /* ── Keyboard shortcuts for Triage tab ── */
  function isTriageActive() {
    for (const btn of document.querySelectorAll('.tabs > .tab-nav > button')) {
      if (btn.classList.contains('selected') && btn.textContent.includes('Triage')) return true;
    }
    return false;
  }
  function isVisible(el) { return el && el.offsetParent !== null; }
  function clickBtn(elemId) {
    const btn = document.querySelector('#' + elemId + ' button');
    if (btn && isVisible(btn) && !btn.disabled) { btn.click(); return true; }
    return false;
  }
  function clickFirstVisible(...ids) {
    for (const id of ids) { if (clickBtn(id)) return; }
  }
  document.addEventListener('keydown', (e) => {
    const tag = e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target.isContentEditable) return;
    if (!isTriageActive()) return;
    switch (e.key) {
      case 'R': e.preventDefault(); clickBtn('pipeline-btn'); break;
      case 'D': e.preventDefault(); clickBtn('dispatch-btn'); break;
      case 'L': e.preventDefault(); clickBtn('learn-btn'); break;
      case 'g': e.preventDefault(); clickBtn('reply-gen-btn'); break;
      case 'a': e.preventDefault(); clickBtn('reply-approve-btn'); break;
      case 's': e.preventDefault(); clickFirstVisible('reply-skip-btn', 'info-skip-btn'); break;
      case 'x': e.preventDefault(); clickFirstVisible('reply-archive-btn', 'info-archive-btn'); break;
      case 'e': e.preventDefault();
        const eb = document.querySelector('#reply-edit-box textarea');
        if (eb && isVisible(eb)) eb.focus();
        break;
      case 'j': case 'ArrowLeft':
        e.preventDefault(); clickFirstVisible('reply-prev-btn', 'info-prev-btn'); break;
      case 'k': case 'ArrowRight':
        e.preventDefault(); clickFirstVisible('reply-next-btn', 'info-next-btn'); break;
    }
  });

  window.addEventListener('resize', fitChatbot);
  const domObs = new MutationObserver(() => {
    hookConnectBtn();
    fitChatbot();
    hideToolbar();
    stampMessages();
    scrollSelectedCard();
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

# ── Chat logic (unchanged) ─────────────────────────────────────────────────────


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
        config.EMAIL = email;  os.environ["EMAIL"] = email
    if app_password:
        config.APP_PASSWORD = app_password;  os.environ["APP_PASSWORD"] = app_password
    if gemini_key:
        config.GEMINI_KEY = gemini_key;  os.environ["GEMINI_KEY"] = gemini_key
    if model:
        config.MODEL = model;  os.environ["MODEL"] = model

    yield (gr.update(), gr.update(), gr.update(), '<p class="st-connecting">⟳ &nbsp;Connecting to Gmail…</p>')

    success, result = initialize()
    if success:
        badge_text = f"● connected  ·  {config.EMAIL}  ·  {config.MODEL}"
        yield (
            gr.update(visible=False),
            gr.update(visible=True, value=badge_text),
            gr.update(visible=True),
            '<p class="st-ok">✓ &nbsp;Connected — ready to use both tabs.</p>',
        )
    else:
        yield (
            gr.update(visible=True),
            gr.update(visible=False),
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
        history.append({"role": "assistant", "content": "Setup required — please fill in your credentials above."})
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


# ── Triage render helpers ──────────────────────────────────────────────────────


def _render_queue_html(queue: list, selected_idx: int) -> str:
    if not queue:
        return '<div class="triage-empty">No emails in queue. Run pipeline to load.</div>'
    items = []
    for i, e in enumerate(queue):
        sel_cls  = " tc-selected" if i == selected_idx else ""
        pri_cls  = " tc-high" if e.get("priority") == "high" else ""
        star     = "★" if e.get("priority") == "high" else "·"
        sender   = _html.escape(tr.extract_name(e.get("from", "Unknown")))
        subject  = _html.escape((e.get("subject") or "(no subject)")[:55])
        reason   = _html.escape((e.get("reason") or "")[:85])
        rel_time = e.get("relative_time", "")
        tc       = e.get("thread_count", 1)
        meta     = f"{rel_time}&nbsp;&nbsp;{tc}↑" if tc > 1 else rel_time
        items.append(
            f'<div class="triage-card{sel_cls}{pri_cls}">'
            f'<div class="tc-header">'
            f'<span class="tc-star">{star}</span>'
            f'<span class="tc-sender">{sender}</span>'
            f'<span class="tc-meta">{meta}</span>'
            f'</div>'
            f'<div class="tc-subject">{subject}</div>'
            + (f'<div class="tc-reason">{reason}</div>' if reason else "")
            + "</div>"
        )
    return f'<div class="triage-queue">{"".join(items)}</div>'


def _render_detail_html(email: dict | None) -> str:
    if not email:
        return '<div class="triage-no-sel">← Select an email to view details</div>'
    priority = email.get("priority", "normal")
    pri_cls  = "td-pri-high" if priority == "high" else "td-pri-normal"
    star     = "★" if priority == "high" else "·"
    pri_lbl  = "HIGH PRIORITY" if priority == "high" else "NORMAL"
    tc       = email.get("thread_count", 1)
    return (
        f'<div class="triage-detail">'
        f'<div class="td-pri-badge {pri_cls}">{star} {pri_lbl}</div>'
        f'<div class="td-from">{_html.escape(email.get("from", ""))}</div>'
        f'<div class="td-subject">{_html.escape(email.get("subject") or "(no subject)")}</div>'
        f'<div class="td-meta">{email.get("relative_time", "")} · {tc} message{"s" if tc != 1 else ""}</div>'
        + (f'<div class="td-reason">{_html.escape(email.get("reason", ""))}</div>' if email.get("reason") else "")
        + "</div>"
    )


def _render_stats_html(stats: dict) -> str:
    if not stats:
        return ""
    if stats.get("error"):
        return f'<div class="pl-stats pl-error">✗ {_html.escape(str(stats["error"]))}</div>'
    l1   = stats.get("layer1_count", 0)
    l2f  = stats.get("layer2_filtered", 0)
    l2s  = stats.get("layer2_surviving", 0)
    l3r  = stats.get("layer3_reply", 0)
    l3i  = stats.get("layer3_info", 0)
    l3n  = stats.get("layer3_noise", 0)
    tok  = stats.get("input_tokens", 0) + stats.get("output_tokens", 0)
    secs = stats.get("elapsed", 0)
    return (
        f'<div class="pl-stats">'
        f'<span class="pl-num">{l1}</span> fetched'
        f' → <span class="pl-num">{l2f}</span> filtered'
        f' → <span class="pl-num">{l2s}</span> to LLM'
        f' → <span class="pl-reply">{l3r} reply</span>'
        f' · <span class="pl-info">{l3i} info</span>'
        f' · <span class="pl-noise">{l3n} noise</span>'
        f'&nbsp;&nbsp;<span class="pl-meta">{tok} tokens · {secs}s</span>'
        f'</div>'
    )


def _render_activity_html(log: list) -> str:
    if not log:
        return '<div class="triage-activity-empty">Activity will appear here.</div>'
    items = []
    for entry in log[-25:]:
        cls = "ta-ok" if entry.startswith("✓") else "ta-warn" if entry.startswith("⏳") else "ta-err" if entry.startswith("✗") else ""
        cls_attr = f' class="ta-item {cls}"' if cls else ' class="ta-item"'
        items.append(f'<div{cls_attr}>{_html.escape(entry)}</div>')
    return f'<div class="triage-activity">{"".join(items)}</div>'


def _add_tokens(tok_state: dict, usage: dict) -> dict:
    return {
        "input":  tok_state.get("input",  0) + usage.get("input",  0),
        "output": tok_state.get("output", 0) + usage.get("output", 0),
    }


def _render_status_bar(tok: dict, last_run: str) -> str:
    total = tok.get("input", 0) + tok.get("output", 0)
    tok_str = f"↑{tok.get('input',0):,} ↓{tok.get('output',0):,} tokens" if total else "0 tokens"
    run_str = f"last pipeline: {last_run}" if last_run else "not run yet"
    return (
        f'<div class="pl-stats" style="margin-bottom:0.5rem">'
        f'<span class="pl-meta">model: </span><span class="pl-num">{_html.escape(config.MODEL)}</span>'
        f'&nbsp;&nbsp;·&nbsp;&nbsp;<span class="pl-meta">session: </span><span class="pl-num">{tok_str}</span>'
        f'&nbsp;&nbsp;·&nbsp;&nbsp;<span class="pl-meta">{run_str}</span>'
        f'</div>'
    )


def _render_learn_html(result: dict, applied: int = -1) -> str:
    if not result:
        return ""
    if result.get("error"):
        return f'<div class="learn-results"><span class="lr-err">✗ {_html.escape(result["error"])}</span></div>'
    parts = ['<div class="learn-results">']
    if result.get("insights"):
        parts.append(f'<div class="lr-insight">{_html.escape(result["insights"])}</div>')
    rules = result.get("rules", [])
    if rules:
        parts.append(f'<div style="font-size:0.65rem;color:var(--muted);letter-spacing:0.1em;margin-bottom:0.4rem">SUGGESTED RULES ({len(rules)})</div>')
        for r in rules:
            parts.append(
                f'<div class="lr-rule">'
                f'<span class="lr-pattern">{_html.escape(r.get("pattern", ""))}</span>'
                f'<span class="lr-reason"> — {_html.escape(r.get("reason", ""))}</span>'
                f'</div>'
            )
    else:
        parts.append('<div style="color:var(--muted)">No new rule suggestions.</div>')
    if applied >= 0:
        parts.append(f'<div class="lr-applied" style="margin-top:0.75rem">✓ {applied} rule{"s" if applied != 1 else ""} added to triage_rules.json</div>')
    parts.append("</div>")
    return "".join(parts)


# ── Triage action handlers ─────────────────────────────────────────────────────


def _remove_and_advance(queue: list, idx: int) -> tuple:
    new_q = [e for i, e in enumerate(queue) if i != idx]
    new_idx = min(idx, max(0, len(new_q) - 1)) if new_q else 0
    return new_q, new_idx


def _pipeline_action(r_q, i_q, r_idx, i_idx, act_log, tok):
    if not _initialized:
        new_log = list(act_log) + ["✗ Not connected — configure credentials first."]
        return (
            "", _render_status_bar(tok, ""),
            r_q, i_q, r_idx, i_idx,
            _render_queue_html(r_q, r_idx),
            _render_queue_html(i_q, i_idx),
            _render_detail_html(r_q[r_idx] if r_q else None),
            _render_detail_html(i_q[i_idx] if i_q else None),
            new_log, tok, "",
        )
    from datetime import datetime as _dt
    stats = run_pipeline()
    new_r_q, new_i_q = load_queues()
    new_r_idx = min(r_idx, max(0, len(new_r_q) - 1)) if new_r_q else 0
    new_i_idx = min(i_idx, max(0, len(new_i_q) - 1)) if new_i_q else 0
    new_log = list(act_log) + [
        f"✓ Pipeline ran in {stats.get('elapsed', 0)}s",
        f"  {stats.get('layer1_count', 0)} fetched → {stats.get('layer2_surviving', 0)} to LLM",
        f"  {stats.get('layer3_reply', 0)} need reply · {stats.get('layer3_info', 0)} informational",
    ]
    if stats.get("error"):
        new_log.append(f"✗ {stats['error']}")
    new_tok = _add_tokens(tok, {"input": stats.get("input_tokens", 0), "output": stats.get("output_tokens", 0)})
    last_run = _dt.now().strftime("%H:%M")
    return (
        _render_stats_html(stats),
        _render_status_bar(new_tok, last_run),
        new_r_q, new_i_q, new_r_idx, new_i_idx,
        _render_queue_html(new_r_q, new_r_idx),
        _render_queue_html(new_i_q, new_i_idx),
        _render_detail_html(new_r_q[new_r_idx] if new_r_q else None),
        _render_detail_html(new_i_q[new_i_idx] if new_i_q else None),
        new_log, new_tok, last_run,
    )


def _navigate(queue: list, idx: int, direction: int) -> tuple:
    if not queue:
        return idx, _render_queue_html(queue, idx), _render_detail_html(None), gr.update(visible=False, value=""), gr.update(visible=False), ""
    new_idx = (idx + direction) % len(queue)
    return (
        new_idx,
        _render_queue_html(queue, new_idx),
        _render_detail_html(queue[new_idx]),
        gr.update(visible=False, value=""),
        gr.update(visible=False),
        "",
    )


def _generate_draft_action(r_q, r_idx, act_log, tok):
    if not r_q or r_idx >= len(r_q):
        yield gr.update(value="No email selected.", visible=True), gr.update(visible=False), act_log, "", tok, _render_status_bar(tok, "")
        return
    email = r_q[r_idx]
    subj = (email.get("subject") or "")[:40]
    yield gr.update(value="⏳ Generating…", visible=True), gr.update(visible=False), list(act_log) + [f"⏳ Drafting reply to: {subj}"], "", tok, _render_status_bar(tok, "")
    draft, usage = tr.generate_draft(email)
    new_tok = _add_tokens(tok, usage)
    new_log = list(act_log) + [f"✓ Draft ready for: {subj}"]
    yield gr.update(value=draft, visible=True), gr.update(visible=True), new_log, draft, new_tok, _render_status_bar(new_tok, "")


def _edit_draft_action(draft, instruction, act_log, tok):
    if not draft or not instruction:
        return gr.update(), draft, act_log, tok, _render_status_bar(tok, "")
    new_draft, usage = tr.edit_draft(draft, instruction)
    new_tok = _add_tokens(tok, usage)
    new_log = list(act_log) + [f"✓ Draft edited: {instruction[:40]}"]
    return gr.update(value=new_draft), new_draft, new_log, new_tok, _render_status_bar(new_tok, "")


def _skip_reply_action(r_q, r_idx, act_log, decisions):
    if not r_q:
        return r_q, r_idx, _render_queue_html(r_q, r_idx), _render_detail_html(None), gr.update(visible=False, value=""), gr.update(visible=False), act_log, decisions
    email = r_q[r_idx]
    tr.log_decision(email["id"], email.get("subject", ""), email.get("from", ""), "skip")
    new_q, new_idx = _remove_and_advance(r_q, r_idx)
    new_log = list(act_log) + [f"· Skipped: {(email.get('subject') or '')[:40]}"]
    new_dec = list(decisions) + [{"email_id": email["id"], "action": "skip"}]
    return (new_q, new_idx, _render_queue_html(new_q, new_idx),
            _render_detail_html(new_q[new_idx] if new_q else None),
            gr.update(visible=False, value=""), gr.update(visible=False), new_log, new_dec)


def _archive_reply_action(r_q, r_idx, act_log, decisions):
    if not r_q:
        return r_q, r_idx, _render_queue_html(r_q, r_idx), _render_detail_html(None), gr.update(visible=False, value=""), gr.update(visible=False), act_log, decisions
    email = r_q[r_idx]
    try:
        tr.archive_in_gmail(email["id"])
        result_msg = f"✓ Archived: {(email.get('subject') or '')[:40]}"
    except Exception as ex:
        result_msg = f"✗ Archive failed: {ex}"
    tr.log_decision(email["id"], email.get("subject", ""), email.get("from", ""), "archive")
    new_q, new_idx = _remove_and_advance(r_q, r_idx)
    new_log = list(act_log) + [result_msg]
    new_dec = list(decisions) + [{"email_id": email["id"], "action": "archive"}]
    return (new_q, new_idx, _render_queue_html(new_q, new_idx),
            _render_detail_html(new_q[new_idx] if new_q else None),
            gr.update(visible=False, value=""), gr.update(visible=False), new_log, new_dec)


def _approve_draft_action(r_q, r_idx, draft, send_q, act_log, decisions):
    if not r_q or not draft:
        return r_q, r_idx, _render_queue_html(r_q, r_idx), _render_detail_html(r_q[r_idx] if r_q else None), gr.update(), gr.update(), send_q, act_log, decisions
    email = r_q[r_idx]
    tr.add_to_send_queue(email, draft)
    new_send_q = tr.load_send_queue()
    tr.log_decision(email["id"], email.get("subject", ""), email.get("from", ""), "approve")
    new_q, new_idx = _remove_and_advance(r_q, r_idx)
    new_log = list(act_log) + [f"✓ Approved: {(email.get('subject') or '')[:40]} → send queue ({len(new_send_q)})"]
    new_dec = list(decisions) + [{"email_id": email["id"], "action": "approve"}]
    return (new_q, new_idx, _render_queue_html(new_q, new_idx),
            _render_detail_html(new_q[new_idx] if new_q else None),
            gr.update(visible=False, value=""), gr.update(visible=False),
            new_send_q, new_log, new_dec)


def _dispatch_action(send_q, act_log):
    if not send_q:
        return send_q, list(act_log) + ["· Send queue is empty."]
    sent, errors = tr.dispatch_all()
    remaining = tr.load_send_queue()
    new_log = list(act_log) + [f"✓ Sent {sent} email{'s' if sent != 1 else ''}."]
    for e in errors:
        new_log.append(f"✗ {e}")
    return remaining, new_log


def _skip_info_action(i_q, i_idx, act_log, decisions):
    if not i_q:
        return i_q, i_idx, _render_queue_html(i_q, i_idx), _render_detail_html(None), act_log, decisions
    email = i_q[i_idx]
    tr.log_decision(email["id"], email.get("subject", ""), email.get("from", ""), "skip")
    new_q, new_idx = _remove_and_advance(i_q, i_idx)
    new_log = list(act_log) + [f"· Skipped: {(email.get('subject') or '')[:40]}"]
    new_dec = list(decisions) + [{"email_id": email["id"], "action": "skip"}]
    return new_q, new_idx, _render_queue_html(new_q, new_idx), _render_detail_html(new_q[new_idx] if new_q else None), new_log, new_dec


def _archive_info_action(i_q, i_idx, act_log, decisions):
    if not i_q:
        return i_q, i_idx, _render_queue_html(i_q, i_idx), _render_detail_html(None), act_log, decisions
    email = i_q[i_idx]
    try:
        tr.archive_in_gmail(email["id"])
        result_msg = f"✓ Archived: {(email.get('subject') or '')[:40]}"
    except Exception as ex:
        result_msg = f"✗ Archive failed: {ex}"
    tr.log_decision(email["id"], email.get("subject", ""), email.get("from", ""), "archive")
    new_q, new_idx = _remove_and_advance(i_q, i_idx)
    new_log = list(act_log) + [result_msg]
    new_dec = list(decisions) + [{"email_id": email["id"], "action": "archive"}]
    return new_q, new_idx, _render_queue_html(new_q, new_idx), _render_detail_html(new_q[new_idx] if new_q else None), new_log, new_dec


def _learn_action(decisions, act_log, tok):
    if len(decisions) < 5:
        msg = f"Need at least 5 decisions (have {len(decisions)})."
        return _render_learn_html({"error": msg, "rules": [], "insights": ""}), [], act_log, tok, _render_status_bar(tok, "")
    result, usage = tr.run_learn_loop()
    new_tok = _add_tokens(tok, usage)
    new_log = list(act_log) + [f"✓ Learn loop: {len(result.get('rules', []))} rule suggestions."]
    return _render_learn_html(result), result.get("rules", []), new_log, new_tok, _render_status_bar(new_tok, "")


def _apply_rules_action(suggestions, act_log):
    if not suggestions:
        return _render_learn_html({"error": "No suggestions to apply.", "rules": []}), act_log
    added = tr.apply_learned_rules(suggestions)
    result = {"insights": "", "rules": suggestions}
    new_log = list(act_log) + [f"✓ {added} rule{'s' if added != 1 else ''} added to triage_rules.json."]
    return _render_learn_html(result, applied=added), new_log


# ── Build UI ───────────────────────────────────────────────────────────────────

success, _ = initialize()
_init_r_q, _init_i_q = load_queues()

with gr.Blocks(title="Gmail Agent", css=CUSTOM_CSS, js=CUSTOM_JS,
               theme=gr.themes.Base(primary_hue=gr.themes.colors.orange, neutral_hue=gr.themes.colors.neutral)) as demo:

    gr.Markdown("◈  GMAIL AGENT", elem_id="ga-header")
    gr.Markdown("natural language interface for your inbox", elem_id="ga-byline")

    # ── Setup panel — shared, above tabs ──────────────────────────────────────
    with gr.Group(visible=not success, elem_id="setup-panel") as setup_panel:
        email_input        = gr.Textbox(label="Gmail Address", placeholder="you@gmail.com", info="The Gmail account you want to connect")
        app_password_input = gr.Textbox(label="App Password", type="password", placeholder="xxxx xxxx xxxx xxxx", info="myaccount.google.com/apppasswords  ·  requires 2-step verification")
        gemini_key_input   = gr.Textbox(label="Gemini API Key", type="password", placeholder="AIza…", info="aistudio.google.com/apikey")
        model_input        = gr.Textbox(label="Model", value=config.MODEL, placeholder="gemma-4-31b-it", info="Leave as-is to use the default")
        setup_btn          = gr.Button("Connect", variant="primary", elem_id="connect-btn")
        setup_status       = gr.HTML("", elem_id="setup-status")

    # Connection badge — shown once connected
    conn_badge = gr.Markdown(
        f"● connected  ·  {config.EMAIL}  ·  {config.MODEL}" if success else "",
        visible=success,
        elem_id="conn-badge",
    )

    with gr.Group(visible=success, elem_id="main-panel") as main_panel:
        with gr.Tabs():

            # ── Tab 1: Chat ────────────────────────────────────────────────────
            with gr.Tab("◈  Chat"):

                chatbot = gr.Chatbot(height=450, layout="panel", show_label=False, render_markdown=True, elem_id="chatbot-wrap")
                thinking_indicator = gr.HTML(THINKING_HTML, visible=False)
                msg = gr.Textbox(show_label=False, placeholder="Ask about your emails…", lines=1, max_lines=4, elem_id="msg-input")

                with gr.Row(elem_id="send-row"):
                    submit_btn = gr.Button("Send",  variant="primary",    scale=4)
                    clear_btn  = gr.Button("Clear", variant="secondary",  scale=1)

                gr.Markdown("↵ Enter to send", elem_id="kb-hint")

            # ── Tab 2: Triage ──────────────────────────────────────────────────────
            with gr.Tab("◈  Triage"):

                # Status / transparency bar
                status_bar_html = gr.HTML(_render_status_bar({"input": 0, "output": 0}, ""))

                # Top bar
                with gr.Row():
                    pipeline_btn        = gr.Button("⟳  Run Pipeline", variant="primary", scale=1, min_width=160, elem_id="pipeline-btn")
                    pipeline_stats_html = gr.HTML(_render_stats_html({}), scale=5)

                with gr.Tabs():

                    # ── Reply queue ────────────────────────────────────────────────
                    with gr.Tab("Reply needed"):
                        with gr.Row():
                            with gr.Column(scale=6):
                                reply_queue_html = gr.HTML(
                                    _render_queue_html(_init_r_q, 0),
                                    elem_id="reply-queue",
                                )
                                with gr.Row():
                                    reply_prev_btn = gr.Button("◀  Prev", variant="secondary", scale=1, elem_id="reply-prev-btn")
                                    reply_next_btn = gr.Button("Next  ▶", variant="secondary", scale=1, elem_id="reply-next-btn")

                            with gr.Column(scale=4):
                                reply_detail_html = gr.HTML(
                                    _render_detail_html(_init_r_q[0] if _init_r_q else None)
                                )
                                with gr.Row():
                                    reply_generate_btn = gr.Button("Generate Draft", variant="primary",   scale=3, elem_id="reply-gen-btn")
                                    reply_skip_btn     = gr.Button("Skip",           variant="secondary", scale=2, elem_id="reply-skip-btn")
                                    reply_archive_btn  = gr.Button("Archive",        variant="secondary", scale=2, elem_id="reply-archive-btn")

                                reply_draft_box = gr.Textbox(
                                    show_label=False, lines=6,
                                    placeholder="Generated draft will appear here…",
                                    visible=False, elem_id="reply-draft",
                                )

                                with gr.Row(visible=False) as reply_approve_row:
                                    reply_approve_btn = gr.Button("✓  Approve",    variant="primary",   scale=2, elem_id="reply-approve-btn")
                                    reply_edit_box    = gr.Textbox(show_label=False, placeholder='"Make it shorter"', scale=3, elem_id="reply-edit-box")
                                    reply_edit_btn    = gr.Button("Edit",           variant="secondary", scale=1)

                                with gr.Row():
                                    dispatch_btn = gr.Button("⬆  Dispatch All", variant="secondary", elem_id="dispatch-btn")

                                reply_activity_html = gr.HTML(
                                    _render_activity_html([]),
                                    elem_id="reply-activity",
                                )

                    # ── Info queue ─────────────────────────────────────────────────
                    with gr.Tab("Informational"):
                        with gr.Row():
                            with gr.Column(scale=6):
                                info_queue_html = gr.HTML(
                                    _render_queue_html(_init_i_q, 0),
                                    elem_id="info-queue",
                                )
                                with gr.Row():
                                    info_prev_btn = gr.Button("◀  Prev", variant="secondary", scale=1, elem_id="info-prev-btn")
                                    info_next_btn = gr.Button("Next  ▶", variant="secondary", scale=1, elem_id="info-next-btn")

                            with gr.Column(scale=4):
                                info_detail_html = gr.HTML(
                                    _render_detail_html(_init_i_q[0] if _init_i_q else None)
                                )
                                with gr.Row():
                                    info_skip_btn    = gr.Button("Skip",    variant="secondary", scale=1, elem_id="info-skip-btn")
                                    info_archive_btn = gr.Button("Archive", variant="secondary", scale=1, elem_id="info-archive-btn")

                                info_activity_html = gr.HTML(
                                    _render_activity_html([]),
                                    elem_id="info-activity",
                                )

                # Learn accordion
                with gr.Accordion("◈  Learn from decisions", open=False):
                    with gr.Row():
                        learn_btn        = gr.Button("Analyse & suggest rules", variant="secondary", scale=2, elem_id="learn-btn")
                        apply_rules_btn  = gr.Button("Apply suggestions",       variant="primary",   scale=1)
                    learn_html = gr.HTML("")

    # ── State ──────────────────────────────────────────────────────────────────
    reply_queue_state = gr.State(_init_r_q)
    info_queue_state  = gr.State(_init_i_q)
    reply_idx_state   = gr.State(0)
    info_idx_state    = gr.State(0)
    send_queue_state  = gr.State(tr.load_send_queue())
    decisions_state   = gr.State([])
    activity_state    = gr.State([])
    draft_state       = gr.State("")
    learn_sugg_state  = gr.State([])
    token_state       = gr.State({"input": 0, "output": 0})
    last_run_state    = gr.State("")

    # ── Chat events ────────────────────────────────────────────────────────────
    setup_btn.click(
        save_credentials,
        inputs=[email_input, app_password_input, gemini_key_input, model_input],
        outputs=[setup_panel, conn_badge, main_panel, setup_status],
    )
    chat_outputs = [chatbot, msg, thinking_indicator]
    submit_btn.click(chat, inputs=[msg, chatbot], outputs=chat_outputs)
    msg.submit(chat,       inputs=[msg, chatbot], outputs=chat_outputs)
    clear_btn.click(lambda: ([], gr.update(visible=False)), outputs=[chatbot, thinking_indicator])

    # ── Pipeline ───────────────────────────────────────────────────────────────
    _pl_inputs  = [reply_queue_state, info_queue_state, reply_idx_state, info_idx_state, activity_state, token_state]
    _pl_outputs = [
        pipeline_stats_html, status_bar_html,
        reply_queue_state, info_queue_state, reply_idx_state, info_idx_state,
        reply_queue_html, info_queue_html,
        reply_detail_html, info_detail_html,
        activity_state, token_state, last_run_state,
    ]
    # ── Keep activity HTML in sync ─────────────────────────────────────────────
    # Chain .then() after each action so the HTML panels update after state settles.
    def _sync_activity(act_log):
        rendered = _render_activity_html(act_log)
        return rendered, rendered

    _nav_r_out  = [reply_idx_state, reply_queue_html, reply_detail_html, reply_draft_box, reply_approve_row, draft_state]
    _skip_r_out = [reply_queue_state, reply_idx_state, reply_queue_html, reply_detail_html, reply_draft_box, reply_approve_row, activity_state, decisions_state]
    _skip_i_out = [info_queue_state, info_idx_state, info_queue_html, info_detail_html, activity_state, decisions_state]

    _sync_args = dict(fn=_sync_activity, inputs=[activity_state], outputs=[reply_activity_html, info_activity_html])

    pipeline_btn.click(_pipeline_action, inputs=_pl_inputs, outputs=_pl_outputs).then(**_sync_args)

    reply_prev_btn.click(lambda q, i: _navigate(q, i, -1), inputs=[reply_queue_state, reply_idx_state], outputs=_nav_r_out)
    reply_next_btn.click(lambda q, i: _navigate(q, i, +1), inputs=[reply_queue_state, reply_idx_state], outputs=_nav_r_out)

    reply_generate_btn.click(_generate_draft_action, inputs=[reply_queue_state, reply_idx_state, activity_state, token_state], outputs=[reply_draft_box, reply_approve_row, activity_state, draft_state, token_state, status_bar_html]).then(**_sync_args)
    reply_edit_btn.click(_edit_draft_action, inputs=[draft_state, reply_edit_box, activity_state, token_state], outputs=[reply_draft_box, draft_state, activity_state, token_state, status_bar_html]).then(**_sync_args)

    reply_skip_btn.click(_skip_reply_action,       inputs=[reply_queue_state, reply_idx_state, activity_state, decisions_state], outputs=_skip_r_out).then(**_sync_args)
    reply_archive_btn.click(_archive_reply_action, inputs=[reply_queue_state, reply_idx_state, activity_state, decisions_state], outputs=_skip_r_out).then(**_sync_args)
    reply_approve_btn.click(_approve_draft_action, inputs=[reply_queue_state, reply_idx_state, draft_state, send_queue_state, activity_state, decisions_state], outputs=[reply_queue_state, reply_idx_state, reply_queue_html, reply_detail_html, reply_draft_box, reply_approve_row, send_queue_state, activity_state, decisions_state]).then(**_sync_args)
    dispatch_btn.click(_dispatch_action, inputs=[send_queue_state, activity_state], outputs=[send_queue_state, activity_state]).then(**_sync_args)

    info_prev_btn.click(lambda q, i: (lambda r: r[:3])(_navigate(q, i, -1)), inputs=[info_queue_state, info_idx_state], outputs=[info_idx_state, info_queue_html, info_detail_html])
    info_next_btn.click(lambda q, i: (lambda r: r[:3])(_navigate(q, i, +1)), inputs=[info_queue_state, info_idx_state], outputs=[info_idx_state, info_queue_html, info_detail_html])

    info_skip_btn.click(_skip_info_action,       inputs=[info_queue_state, info_idx_state, activity_state, decisions_state], outputs=_skip_i_out).then(**_sync_args)
    info_archive_btn.click(_archive_info_action, inputs=[info_queue_state, info_idx_state, activity_state, decisions_state], outputs=_skip_i_out).then(**_sync_args)

    learn_btn.click(_learn_action, inputs=[decisions_state, activity_state, token_state], outputs=[learn_html, learn_sugg_state, activity_state, token_state, status_bar_html]).then(**_sync_args)
    apply_rules_btn.click(_apply_rules_action, inputs=[learn_sugg_state, activity_state], outputs=[learn_html, activity_state]).then(**_sync_args)


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
