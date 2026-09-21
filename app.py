import asyncio
import os
from pathlib import Path

import streamlit as st
from agent_framework.foundry import FoundryAgent
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from history_store import ConversationStore

load_dotenv()

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
AGENT_NAME = "IT-Helpdesk-Agent"
AGENT_VERSION = os.getenv("FOUNDRY_AGENT_VERSION") or None

STORE = ConversationStore(Path(__file__).with_name("chat_history.db"))

MAX_CONTEXT_MESSAGES = 12
MAX_CONTEXT_CHARS = 12000


async def get_agent_response(prompt, session):
    async with FoundryAgent(
        project_endpoint=PROJECT_ENDPOINT,
        agent_name=AGENT_NAME,
        agent_version=AGENT_VERSION,
        credential=DefaultAzureCredential(),
    ) as agent:
        if session is None:
            session = agent.create_session()

        response = await agent.run(prompt, session=session)
        return str(response), session


def start_new_conversation():
    st.session_state.conversation_id = None
    st.session_state.messages = []
    st.session_state.agent_session = None
    st.session_state.page = "active"


def load_conversation(conversation_id):
    messages = STORE.load_messages(conversation_id)

    if not messages:
        start_new_conversation()
        return

    st.session_state.conversation_id = conversation_id
    st.session_state.messages = messages
    st.session_state.agent_session = None
    st.session_state.page = "active"


def ensure_session_state():
    defaults = {
        "conversation_id": None,
        "messages": [],
        "agent_session": None,
        "page": "active",
        "theme": "dark",
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def prompt_with_saved_context(messages, prompt):
    if not messages:
        return prompt

    selected = messages[-MAX_CONTEXT_MESSAGES:]
    parts = []
    total = 0

    for message in reversed(selected):
        part = f"{message['role'].title()}: {message['content'].strip()}"

        if total + len(part) > MAX_CONTEXT_CHARS:
            remaining = MAX_CONTEXT_CHARS - total
            if remaining > 80:
                parts.append(part[:remaining] + "...")
            break

        parts.append(part)
        total += len(part)

    newline = chr(10)
    transcript = newline.join(reversed(parts))

    return (
        "Continue the following IT helpdesk conversation. "
        "Use it only as context and answer the latest request. "
        "Do not mention this context block."
        + newline + newline
        + "Previous conversation:" + newline
        + transcript
        + newline + newline
        + "Latest user request: " + prompt
    )


def local_troubleshooting_response(prompt):
    request = prompt.lower()

    if any(x in request for x in ("internet", "wi-fi", "wifi", "network")):
        steps = [
            "Check that airplane mode is off and reconnect to the Wi-Fi network.",
            "Check whether other devices are also offline.",
            "Restart your computer and run the network troubleshooter.",
            "Record the exact error and network name if the issue continues.",
        ]
    elif "vpn" in request:
        steps = [
            "Confirm that your normal internet connection works.",
            "Disconnect and reconnect the VPN once.",
            "Verify your approved sign-in details.",
            "Record the exact VPN error and contact IT if it continues.",
        ]
    elif any(x in request for x in ("password", "login", "sign in", "account")):
        steps = [
            "Use the approved password-reset process and never share your password.",
            "Check Caps Lock and confirm the correct work account.",
            "Verify your internet connection if MFA approval does not arrive.",
            "Contact IT if the account remains inaccessible.",
        ]
    else:
        steps = [
            "Restart the affected application or device.",
            "Check whether the issue affects other applications or devices.",
            "Record the exact error message and when the issue started.",
            "Contact IT with those details if the issue continues.",
        ]

    return (
        "Microsoft Foundry is currently unavailable. "
        "Here is first-line troubleshooting guidance:\n\n"
        + "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1))
    )


st.set_page_config(
    page_title="IT Helpdesk",
    page_icon="⚡",
    layout="wide",
)

ensure_session_state()

is_dark = st.session_state.theme == "dark"

if is_dark:
    colors = {
        "bg": "#212121",
        "surface": "#171717",
        "surface2": "#2f2f2f",
        "surface_card": "#262626",
        "hover": "#333333",
        "border": "rgba(255, 255, 255, 0.08)",
        "border2": "rgba(255, 255, 255, 0.15)",
        "text": "#ececec",
        "muted": "#b4b4b4",
        "dim": "#71717a",
        "accent": "#10a37f",
        "accent_hover": "#0e8e6e",
        "user_bubble": "#2f2f2f",
        "shadow": "rgba(0, 0, 0, 0.35)",
    }
else:
    colors = {
        "bg": "#ffffff",
        "surface": "#f9f9fb",
        "surface2": "#f0f0f4",
        "surface_card": "#ffffff",
        "hover": "#eaeaf0",
        "border": "#e5e7eb",
        "border2": "#d1d5db",
        "text": "#111827",
        "muted": "#4b5563",
        "dim": "#9ca3af",
        "accent": "#0d9488",
        "accent_hover": "#0f766e",
        "user_bubble": "#f3f4f6",
        "shadow": "rgba(0, 0, 0, 0.06)",
    }

st.markdown(
f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

:root {{
  --bg: {colors["bg"]};
  --surface: {colors["surface"]};
  --surface2: {colors["surface2"]};
  --surface-card: {colors["surface_card"]};
  --hover: {colors["hover"]};
  --border: {colors["border"]};
  --border2: {colors["border2"]};
  --text: {colors["text"]};
  --muted: {colors["muted"]};
  --dim: {colors["dim"]};
  --accent: {colors["accent"]};
  --accent-hover: {colors["accent_hover"]};
  --user-bubble: {colors["user_bubble"]};
  --shadow: {colors["shadow"]};
}}

html, body, .stApp, [class*="css"] {{
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}}

.stApp {{
  background-color: var(--bg) !important;
  color: var(--text) !important;
}}

/* REFINED HEADER & FIXED TOGGLE ICON */
[data-testid="stHeader"] {{
  background: transparent !important;
  border: none !important;
  height: 0px !important;
  z-index: 1000 !important;
}}

[data-testid="collapsedControl"] {{
  position: fixed !important;
  top: 14px !important;
  left: 16px !important;
  background-color: #262626 !important; /* Forces a dark button to highlight the white arrow */
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
  border-radius: 8px !important;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25) !important;
  z-index: 9999 !important;
  padding: 6px !important;
  margin: 0 !important;
  transition: background-color 0.2s ease !important;
}}

[data-testid="collapsedControl"]:hover {{
  background-color: #404040 !important;
}}

[data-testid="collapsedControl"] svg {{
  fill: #ffffff !important; 
  color: #ffffff !important;
}}

.top-header-main {{
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 24px 16px 64px; /* Left padding ensures it clears the toggle arrow */
  border-bottom: 1px solid var(--border);
  background-color: var(--bg);
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 998;
  height: 64px;
}}
/* END HEADER CSS */

#MainMenu, footer {{
  visibility: hidden !important;
}}

[data-testid="stSidebar"] {{
  background-color: var(--surface) !important;
  border-right: 1px solid var(--border) !important;
  min-width: 260px !important;
  max-width: 290px !important;
  z-index: 9999 !important;
}}

[data-testid="stSidebar"] > div:first-child {{
  padding: 16px 12px 14px !important;
}}

.brand-wrapper {{
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 8px 16px 8px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 14px;
}}

.brand-icon {{
  width: 28px;
  height: 28px;
  border-radius: 7px;
  background: var(--surface2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
}}

.brand-title {{
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  letter-spacing: -0.01em;
}}

.sidebar-category {{
  margin: 16px 8px 6px 8px;
  font-size: 11px;
  font-weight: 600;
  color: var(--dim);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}}

[data-testid="stSidebar"] .stButton {{
  margin-bottom: 3px !important;
}}

[data-testid="stSidebar"] .stButton > button {{
  width: 100% !important;
  height: 38px !important;
  min-height: 38px !important;
  margin: 0 !important;
  padding: 8px 12px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: flex-start !important;
  text-align: left !important;
  border: 1px solid transparent !important;
  border-radius: 8px !important;
  background-color: transparent !important;
  color: var(--muted) !important;
  font-size: 13px !important;
  font-weight: 500 !important;
  transition: background-color 0.15s ease, color 0.15s ease, border-color 0.15s ease !important;
}}

[data-testid="stSidebar"] .stButton > button div,
[data-testid="stSidebar"] .stButton > button p,
[data-testid="stSidebar"] .stButton > button span {{
  width: 100% !important;
  text-align: left !important;
  justify-content: flex-start !important;
  margin: 0 !important;
  display: block !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  white-space: nowrap !important;
}}

[data-testid="stSidebar"] .stButton > button:hover {{
  background-color: var(--hover) !important;
  color: var(--text) !important;
}}

[data-testid="stSidebar"] button[kind="primary"] {{
  background-color: var(--surface2) !important;
  border: 1px solid var(--border2) !important;
  color: var(--text) !important;
  margin-bottom: 8px !important;
}}

[data-testid="stSidebar"] button[kind="primary"]:hover {{
  background-color: var(--hover) !important;
  border-color: var(--border2) !important;
}}

.block-container {{
  max-width: 820px !important;
  margin: 0 auto !important;
  padding: 100px 24px 130px 24px !important; /* Increased top padding to clear the fixed header */
}}

.hero-box {{
  text-align: center;
  padding: 48px 12px 28px;
}}

.hero-badge {{
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 5px 12px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  color: var(--muted);
  margin-bottom: 16px;
}}

.status-dot {{
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background-color: var(--accent);
}}

.hero-title {{
  font-size: 28px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 8px;
  letter-spacing: -0.02em;
}}

.hero-desc {{
  font-size: 14px;
  color: var(--muted);
  max-width: 460px;
  margin: 0 auto;
  line-height: 1.5;
}}

.main-view-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 14px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--border);
}}

.view-heading {{
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
}}

.status-indicator {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
}}

[data-testid="stMainBlockContainer"] .stButton > button {{
  background-color: var(--surface-card) !important;
  border: 1px solid var(--border) !important;
  color: var(--text) !important;
  border-radius: 12px !important;
  padding: 16px !important;
  min-height: 80px !important;
  display: flex !important;
  flex-direction: column !important;
  justify-content: center !important;
  align-items: flex-start !important;
  text-align: left !important;
  transition: all 0.2s ease !important;
  box-shadow: 0 2px 8px var(--shadow) !important;
}}

[data-testid="stMainBlockContainer"] .stButton > button:hover {{
  background-color: var(--hover) !important;
  border-color: var(--border2) !important;
  transform: translateY(-1px) !important;
}}

[data-testid="stMainBlockContainer"] .stButton > button p {{
  color: var(--text) !important;
  white-space: pre-wrap !important;
  line-height: 1.5 !important;
  margin: 0 !important;
}}

[data-testid="stChatMessage"] {{
  background: transparent !important;
  border: none !important;
  padding: 14px 4px !important;
  margin: 0 auto !important;
}}

[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li {{
  font-size: 14.5px !important;
  line-height: 1.65 !important;
  color: var(--text) !important;
}}

[data-testid="stChatMessage"] pre, [data-testid="stChatMessage"] code {{
  font-family: 'JetBrains Mono', monospace !important;
  font-size: 13px !important;
}}

[data-testid="stBottom"] {{
  background: var(--bg) !important;
  border: none !important;
}}

[data-testid="stBottom"] > div {{
  background: transparent !important;
}}

[data-testid="stChatInput"] {{
  max-width: 820px !important;
  margin: 0 auto !important;
  padding: 10px 0 16px 0 !important;
  background: transparent !important;
}}

[data-testid="stChatInput"] > div {{
  background-color: var(--surface2) !important;
  border: 1px solid var(--border2) !important;
  border-radius: 20px !important;
  padding: 4px 10px !important;
  box-shadow: 0 4px 20px var(--shadow) !important;
}}

[data-testid="stChatInput"] > div:focus-within {{
  border-color: var(--accent) !important;
}}

[data-testid="stChatInput"] textarea {{
  font-size: 14px !important;
  color: var(--text) !important;
  background: transparent !important;
}}

[data-testid="stChatInput"] textarea::placeholder {{
  color: var(--dim) !important;
}}

[data-testid="stChatInput"] button {{
  background-color: var(--accent) !important;
  color: #ffffff !important;
  border: none !important;
  border-radius: 12px !important;
  transition: background-color 0.15s ease !important;
}}

[data-testid="stChatInput"] button:hover {{
  background-color: var(--accent-hover) !important;
}}
</style>
""",
unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="top-header-main">
        <div class="brand-icon">⚡</div>
        <div class="brand-title">IT Helpdesk</div>
    </div>
    """,
    unsafe_allow_html=True,
)


with st.sidebar:
    st.markdown(
        """
        <div class="brand-wrapper">
          <div class="brand-icon">⚡</div>
          <div class="brand-title">IT Helpdesk</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("＋  New chat", use_container_width=True, type="primary"):
        start_new_conversation()
        st.rerun()

    st.markdown('<div class="sidebar-category">Recents</div>', unsafe_allow_html=True)

    conversations = STORE.list_conversations()

    if conversations:
        for conversation in conversations[:10]:
            is_current = conversation["id"] == st.session_state.conversation_id
            prefix = "●  " if is_current else "💬  "
            title = prefix + conversation["title"]
            if len(title) > 30:
                title = title[:28] + "..."

            if st.button(
                title,
                key=f"recent-{conversation['id']}",
                use_container_width=True,
            ):
                load_conversation(conversation["id"])
                st.rerun()
    else:
        st.caption("No conversations yet.")

    st.markdown('<div class="sidebar-category">Settings</div>', unsafe_allow_html=True)

    if st.button("🗂️  All chat history", use_container_width=True):
        st.session_state.page = "history"
        st.rerun()

    theme_toggle_label = "☀️  Light mode" if is_dark else "🌙  Dark mode"
    if st.button(theme_toggle_label, use_container_width=True):
        st.session_state.theme = "light" if is_dark else "dark"
        st.rerun()


if st.session_state.page == "history":
    st.markdown(
        """
        <div class="main-view-header">
          <div class="view-heading">Conversation Archive</div>
          <div class="status-indicator">All Saved Sessions</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not conversations:
        st.info("No saved conversations yet.")
    else:
        for conversation in conversations:
            if st.button(
                f"💬  {conversation['title']}",
                key=f"history-{conversation['id']}",
                use_container_width=True,
            ):
                load_conversation(conversation["id"])
                st.rerun()

    st.stop()


selected_quick_prompt = None

if not st.session_state.messages:
    st.markdown(
        """
        <div class="hero-box">
          <div class="hero-badge">
            <span class="status-dot"></span>
            <span>IT support ready</span>
          </div>
          <div class="hero-title">Where can we help you today?</div>
          <div class="hero-desc">Ask a diagnostic question, check network status, or initiate step-by-step troubleshooting.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button(
            "📶  Wi-Fi Connected but No Internet\nDiagnose gateway & DNS configuration",
            key="card_wifi",
            use_container_width=True,
        ):
            selected_quick_prompt = "My Wi-Fi is connected but the internet is not working."
        if st.button(
            "🔑  Password Reset & MFA\nRecover account access or verify authenticator",
            key="card_pwd",
            use_container_width=True,
        ):
            selected_quick_prompt = "I need help resetting my work password and signing in."
    with col2:
        if st.button(
            "🛡️  VPN Connection Troubles\nResolve timeout and authentication drops",
            key="card_vpn",
            use_container_width=True,
        ):
            selected_quick_prompt = "My VPN is disconnecting and failing to authenticate."
        if st.button(
            "⚡  Application Crash or Hang\nRemediate unresponsive workplace software",
            key="card_app",
            use_container_width=True,
        ):
            selected_quick_prompt = "My required work application is crashing immediately on launch."
else:
    st.markdown(
        """
        <div class="main-view-header">
          <div class="view-heading">IT Diagnostics Console</div>
          <div class="status-indicator">
            <span class="status-dot"></span>
            <span>IT support ready</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

user_input = st.chat_input("Message IT Helpdesk...")
active_prompt = selected_quick_prompt or user_input

if active_prompt:
    if st.session_state.conversation_id is None:
        st.session_state.conversation_id = STORE.create_conversation()

    conversation_id = st.session_state.conversation_id

    user_message = STORE.append_message(
        conversation_id,
        "user",
        active_prompt,
    )
    st.session_state.messages.append(user_message)

    with st.chat_message("user"):
        st.markdown(active_prompt)

    with st.chat_message("assistant"):
        try:
            agent_prompt = active_prompt

            if (
                st.session_state.agent_session is None
                and len(st.session_state.messages) > 1
            ):
                agent_prompt = prompt_with_saved_context(
                    st.session_state.messages[:-1],
                    active_prompt,
                )

            answer, session = asyncio.run(
                get_agent_response(
                    agent_prompt,
                    st.session_state.agent_session,
                )
            )
            st.session_state.agent_session = session

        except Exception:
            st.warning(
                "Microsoft Foundry could not be reached. "
                "Using local troubleshooting guidance."
            )
            answer = local_troubleshooting_response(active_prompt)

        st.markdown(answer)

        assistant_message = STORE.append_message(
            conversation_id,
            "assistant",
            answer,
        )
        st.session_state.messages.append(assistant_message)

    st.rerun()