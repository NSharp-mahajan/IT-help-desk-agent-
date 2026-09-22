import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter

import streamlit as st
from agent_framework.foundry import FoundryAgent
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from history_store import ConversationStore
from telemetry_store import TelemetryStore

load_dotenv()

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
AGENT_NAME = "IT-Helpdesk-Agent"
AGENT_VERSION = os.getenv("FOUNDRY_AGENT_VERSION") or None

STORE = ConversationStore(Path(__file__).with_name("chat_history.db"))
TELEMETRY = TelemetryStore(Path(__file__).with_name("chat_history.db"))

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
    st.session_state.pending_feedback_request_id = None
    st.session_state.page = "active"


def show_analytics():
    """Render analytics from request events, conversations, feedback, and tickets."""
    st.markdown(
        """
        <div class="main-view-header">
          <div class="view-heading">IT Support Analytics Dashboard</div>
          <div class="status-indicator">Aggregated support metrics & observability</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    ranges = {
        "Last 24 hours": timedelta(hours=24),
        "Last 7 days": timedelta(days=7),
        "Last 30 days": timedelta(days=30),
        "All time": None,
    }
    selected_range = st.selectbox("Time range", tuple(ranges), index=2)
    duration = ranges[selected_range]
    start_at = None if duration is None else (datetime.now(UTC) - duration).isoformat()

    summary = TELEMETRY.summary(start_at)
    total_requests = summary["total_requests"]
    total_conversations = TELEMETRY.conversation_count(start_at)
    ticket_count = TELEMETRY.ticket_count(start_at)
    success_rate = summary["agent_success_rate"]
    success_rate_display = "—" if success_rate is None else f"{success_rate:.1f}%"

    st.markdown("### Support Overview")
    kpi_cols = st.columns(4)
    kpi_cols[0].metric("Support conversations", total_conversations)
    kpi_cols[1].metric("Support requests", total_requests)
    kpi_cols[2].metric("Support tickets", ticket_count)
    kpi_cols[3].metric("Agent success rate", success_rate_display)

    st.markdown("---")

    # Resolved vs Escalated issues
    st.subheader("Resolved vs Escalated Issues")
    comp = TELEMETRY.resolution_vs_escalation(start_at)
    res_rate_display = "—" if comp["resolution_rate"] is None else f"{comp['resolution_rate']:.1f}%"
    esc_rate_display = "—" if comp["escalation_rate"] is None else f"{comp['escalation_rate']:.1f}%"

    res_cols = st.columns(4)
    res_cols[0].metric("Resolved issues", comp["resolved_count"])
    res_cols[1].metric("Escalated issues", comp["escalated_count"])
    res_cols[2].metric("Resolution rate", res_rate_display)
    res_cols[3].metric("Escalation rate", esc_rate_display)

    if comp["total_cases"] > 0:
        comparison_data = [
            {"Status": "Resolved", "Cases": comp["resolved_count"]},
            {"Status": "Escalated", "Cases": comp["escalated_count"]},
        ]
        st.bar_chart(comparison_data, x="Status", y="Cases")
        st.caption("Compares user-confirmed issue resolutions against unresolved issues requiring escalation.")
    else:
        st.info("No resolution or escalation outcomes recorded for this time period.")

    st.markdown("---")

    # Issue Category Distribution & Most Common IT Categories
    st.subheader("Issue Categories")
    categories = TELEMETRY.category_distribution(start_at)
    top_category = TELEMETRY.most_common_category(start_at)

    cat_cols = st.columns(2)
    with cat_cols[0]:
        if top_category:
            top_desc = f"{top_category['label']} ({top_category['requests']} requests, {top_category['percentage']}%)"
        else:
            top_desc = "None recorded"
        st.metric("Most common issue category", top_desc)

    with cat_cols[1]:
        categorized_count = sum(c["requests"] for c in categories) if categories else 0
        st.metric("Categorized issues", categorized_count)

    if categories:
        cat_chart_data = [{"Category": row["label"], "Requests": row["requests"]} for row in categories]
        st.bar_chart(cat_chart_data, x="Category", y="Requests")
        st.dataframe(
            [{"Category": row["label"], "Requests": row["requests"]} for row in categories],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No categorized issue requests recorded in this period.")

    st.markdown("---")

    # Basic usage trends over time
    st.subheader("Usage Trends Over Time")
    trends = TELEMETRY.usage_trends(start_at)
    if trends:
        st.bar_chart(trends, x="day", y="requests")
        st.caption("Daily request activity over the selected time range.")
    else:
        st.info("No usage activity recorded for this period.")

    st.markdown("---")

    # Performance & Observability
    st.subheader("System Performance & Reliability")
    average_latency = summary["average_latency_ms"]
    latency_display = "—" if average_latency is None else f"{average_latency / 1000:.2f} s"
    p95_latency = summary["p95_latency_ms"]
    p95_display = "—" if p95_latency is None else f"{p95_latency / 1000:.2f} s"

    perf_cols = st.columns(3)
    perf_cols[0].metric("Successful agent requests", summary["successful_requests"])
    perf_cols[1].metric("Fallback requests", summary["failed_requests"])
    perf_cols[2].metric("Average response latency", latency_display)

    failures = TELEMETRY.failure_breakdown(start_at)
    if failures:
        st.write("**Failure observability**")
        st.dataframe(failures, use_container_width=True, hide_index=True)
        st.caption("Failure details include stage, sanitized exception type, and average response latency.")
    else:
        st.success("No Foundry service failures recorded.")

    st.caption(
        "Privacy guarantee: Analytics dashboard aggregates application metrics only. "
        "Prompts, user messages, free-form feedback text, and credentials are never stored in or exposed by analytics."
    )


def load_conversation(conversation_id):
    messages = STORE.load_messages(conversation_id)

    if not messages:
        start_new_conversation()
        return

    st.session_state.conversation_id = conversation_id
    st.session_state.messages = messages
    st.session_state.agent_session = None
    try:
        st.session_state.pending_feedback_request_id = TELEMETRY.latest_request_id(conversation_id)
    except Exception:
        st.session_state.pending_feedback_request_id = None
    st.session_state.page = "active"


def ensure_session_state():
    defaults = {
        "conversation_id": None,
        "messages": [],
        "agent_session": None,
        "pending_feedback_request_id": None,
        "page": "active",
        "theme": "dark",
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def show_resolution_feedback():
    """Offer explicit resolution feedback for the latest exact support request."""
    request_id = st.session_state.pending_feedback_request_id
    if request_id is None:
        return

    try:
        feedback = TELEMETRY.feedback_for_request(request_id)
    except Exception:
        st.caption("Feedback is temporarily unavailable. Your support chat is unaffected.")
        return
    st.markdown("**Resolution Confirmation** &mdash; *Was this guidance helpful in resolving your issue?*")
    if feedback is not None:
        confirmation = (
            "Thanks for confirming that your issue was resolved."
            if feedback["resolution_status"] == "resolved"
            else "Thanks for letting us know you still need help."
        )
        st.success(confirmation)
        return

    feedback_text = st.text_area(
        "Optional feedback",
        key=f"feedback-comment-{request_id}",
        max_chars=TelemetryStore.MAX_FEEDBACK_TEXT_LENGTH,
        placeholder="Add a short comment if you would like to share more context.",
        height=80,
    )
    resolved_column, unresolved_column = st.columns(2)
    selected_status = None
    with resolved_column:
        if st.button("Mark as Resolved", key=f"feedback-resolved-{request_id}"):
            selected_status = "resolved"
    with unresolved_column:
        if st.button("Request Escalation", key=f"feedback-unresolved-{request_id}"):
            selected_status = "not_resolved"

    if selected_status is None:
        return
    try:
        TELEMETRY.record_feedback(request_id, selected_status, feedback_text)
    except ValueError:
        st.info("Feedback was already recorded for this support request.")
    except Exception:
        st.warning("Feedback could not be saved. Your support chat is unaffected; please try again.")
    else:
        st.success("Thanks for your feedback.")


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
        category = "network"
        steps = [
            "Check that airplane mode is off and reconnect to the Wi-Fi network.",
            "Check whether other devices are also offline.",
            "Restart your computer and run the network troubleshooter.",
            "Record the exact error and network name if the issue continues.",
        ]
    elif "vpn" in request:
        category = "vpn"
        steps = [
            "Confirm that your normal internet connection works.",
            "Disconnect and reconnect the VPN once.",
            "Verify your approved sign-in details.",
            "Record the exact VPN error and contact IT if it continues.",
        ]
    elif any(x in request for x in ("password", "login", "sign in", "account")):
        category = "account"
        steps = [
            "Use the approved password-reset process and never share your password.",
            "Check Caps Lock and confirm the correct work account.",
            "Verify your internet connection if MFA approval does not arrive.",
            "Contact IT if the account remains inaccessible.",
        ]
    else:
        category = "general"
        steps = [
            "Restart the affected application or device.",
            "Check whether the issue affects other applications or devices.",
            "Record the exact error message and when the issue started.",
            "Contact IT with those details if the issue continues.",
        ]

    response = (
        "Microsoft Foundry is currently unavailable. "
        "Here is first-line troubleshooting guidance:\n\n"
        + "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1))
    )
    return response, category


USER_AVATAR = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%2394a3b8'>"
    "<path d='M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z'/>"
    "</svg>"
)

ASSISTANT_AVATAR = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%2310b981'>"
    "<path d='M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5'/>"
    "</svg>"
)


st.set_page_config(
    page_title="IT Helpdesk | AI Diagnostics",
    layout="wide",
)

ensure_session_state()

is_dark = st.session_state.theme == "dark"

if is_dark:
    colors = {
        "bg": "#0e1015",
        "surface": "#161922",
        "surface2": "#1e222e",
        "surface_card": "#181c26",
        "hover": "#252b3b",
        "border": "rgba(255, 255, 255, 0.08)",
        "border2": "rgba(255, 255, 255, 0.16)",
        "text": "#f3f4f6",
        "muted": "#9ca3af",
        "dim": "#6b7280",
        "accent": "#10b981",
        "accent_hover": "#059669",
        "user_bubble": "#1e222e",
        "shadow": "rgba(0, 0, 0, 0.45)",
    }
else:
    colors = {
        "bg": "#f8fafc",
        "surface": "#ffffff",
        "surface2": "#f1f5f9",
        "surface_card": "#ffffff",
        "hover": "#e2e8f0",
        "border": "#e2e8f0",
        "border2": "#cbd5e1",
        "text": "#0f172a",
        "muted": "#475569",
        "dim": "#94a3b8",
        "accent": "#059669",
        "accent_hover": "#047857",
        "user_bubble": "#f1f5f9",
        "shadow": "rgba(0, 0, 0, 0.06)",
    }

st.markdown(
f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

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
  background-color: var(--surface2) !important;
  border: 1px solid var(--border2) !important;
  border-radius: 8px !important;
  box-shadow: 0 4px 12px var(--shadow) !important;
  z-index: 9999 !important;
  padding: 6px !important;
  margin: 0 !important;
  transition: background-color 0.2s ease !important;
}}

[data-testid="collapsedControl"]:hover {{
  background-color: var(--hover) !important;
}}

[data-testid="collapsedControl"] svg {{
  fill: #ffffff !important; 
  color: #ffffff !important;
}}

.top-header-main {{
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 24px 16px 64px;
  border-bottom: 1px solid var(--border);
  background-color: var(--bg);
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 998;
  height: 64px;
}}

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
  gap: 12px;
  padding: 4px 8px 16px 8px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 14px;
}}

.brand-icon {{
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--surface2);
  border: 1px solid var(--border2);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}}

.brand-title {{
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  letter-spacing: -0.01em;
  line-height: 1.2;
}}

.brand-tag {{
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--dim);
  font-weight: 600;
}}

.sidebar-category {{
  margin: 18px 8px 6px 8px;
  font-size: 10px;
  font-weight: 700;
  color: var(--dim);
  text-transform: uppercase;
  letter-spacing: 0.08em;
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
  transition: all 0.15s ease !important;
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
  font-weight: 600 !important;
}}

[data-testid="stSidebar"] button[kind="primary"]:hover {{
  background-color: var(--hover) !important;
  border-color: var(--accent) !important;
}}

.block-container {{
  max-width: 820px !important;
  margin: 0 auto !important;
  padding: 100px 24px 130px 24px !important;
}}

.hero-box {{
  text-align: center;
  padding: 44px 12px 28px;
}}

.hero-badge {{
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  background: var(--surface2);
  border: 1px solid var(--border2);
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  margin-bottom: 16px;
}}

.status-pulse {{
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background-color: var(--accent);
  box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
  animation: pulse-indicator 2s infinite cubic-bezier(0.66, 0, 0, 1);
  display: inline-block;
}}

@keyframes pulse-indicator {{
  0% {{ box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }}
  70% {{ box-shadow: 0 0 0 7px rgba(16, 185, 129, 0); }}
  100% {{ box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }}
}}

.hero-title {{
  font-size: 28px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 8px;
  letter-spacing: -0.02em;
}}

.hero-desc {{
  font-size: 14px;
  color: var(--muted);
  max-width: 480px;
  margin: 0 auto;
  line-height: 1.55;
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
  gap: 8px;
  font-size: 12px;
  color: var(--muted);
}}

[data-testid="stMainBlockContainer"] .stButton > button {{
  background-color: var(--surface-card) !important;
  border: 1px solid var(--border) !important;
  color: var(--text) !important;
  border-radius: 12px !important;
  padding: 16px 20px !important;
  min-height: 84px !important;
  display: flex !important;
  flex-direction: column !important;
  justify-content: center !important;
  align-items: flex-start !important;
  text-align: left !important;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
  box-shadow: 0 2px 8px var(--shadow) !important;
}}

[data-testid="stMainBlockContainer"] .stButton > button:hover {{
  background-color: var(--surface2) !important;
  border-color: var(--accent) !important;
  transform: translateY(-2px) !important;
  box-shadow: 0 8px 24px var(--shadow) !important;
}}

[data-testid="stMainBlockContainer"] .stButton > button p {{
  color: var(--text) !important;
  white-space: pre-wrap !important;
  line-height: 1.5 !important;
  margin: 0 !important;
}}

.diagnostic-banner {{
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.25);
  border-radius: 8px;
  font-size: 13px;
  color: #fbbf24;
  margin: 12px 0 16px 0;
  line-height: 1.4;
}}

.diagnostic-badge {{
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
  padding: 3px 8px;
  border-radius: 4px;
  background: rgba(245, 158, 11, 0.2);
  color: #fbbf24;
  white-space: nowrap;
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
        <div class="brand-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
                <path d="M2 17l10 5 10-5"></path>
                <path d="M2 12l10 5 10-5"></path>
            </svg>
        </div>
        <div class="brand-title">IT Helpdesk Console</div>
    </div>
    """,
    unsafe_allow_html=True,
)


with st.sidebar:
    st.markdown(
        """
        <div class="brand-wrapper">
          <div class="brand-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
                <path d="M2 17l10 5 10-5"></path>
                <path d="M2 12l10 5 10-5"></path>
            </svg>
          </div>
          <div>
            <div class="brand-title">IT Helpdesk</div>
            <div class="brand-tag">AI Diagnostics</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("+  New conversation", use_container_width=True, type="primary"):
        start_new_conversation()
        st.rerun()

    st.markdown('<div class="sidebar-category">Recent Sessions</div>', unsafe_allow_html=True)

    conversations = STORE.list_conversations()

    if conversations:
        for conversation in conversations[:10]:
            is_current = conversation["id"] == st.session_state.conversation_id
            prefix = "•  " if is_current else "   "
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

    st.markdown('<div class="sidebar-category">Navigation</div>', unsafe_allow_html=True)

    if st.button("Conversation archive", use_container_width=True):
        st.session_state.page = "history"
        st.rerun()

    if st.button("Support analytics", use_container_width=True):
        st.session_state.page = "analytics"
        st.rerun()

    theme_toggle_label = "Switch to light theme" if is_dark else "Switch to dark theme"
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
                f"•  {conversation['title']}",
                key=f"history-{conversation['id']}",
                use_container_width=True,
            ):
                load_conversation(conversation["id"])
                st.rerun()

    st.stop()

if st.session_state.page == "analytics":
    show_analytics()
    st.stop()


selected_quick_prompt = None

if not st.session_state.messages:
    st.markdown(
        """
        <div class="hero-box">
          <div class="hero-badge">
            <span class="status-pulse"></span>
            <span>IT support ready</span>
          </div>
          <div class="hero-title">IT Diagnostics Console</div>
          <div class="hero-desc">Ask a diagnostic question, check network status, or initiate automated troubleshooting.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button(
            "NETWORK: Wi-Fi & Connectivity\nDiagnose gateway routing & DNS configuration",
            key="card_wifi",
            use_container_width=True,
        ):
            selected_quick_prompt = "My Wi-Fi is connected but the internet is not working."
        if st.button(
            "ACCESS: Password Reset & MFA\nRecover account access or verify authenticator",
            key="card_pwd",
            use_container_width=True,
        ):
            selected_quick_prompt = "I need help resetting my work password and signing in."
    with col2:
        if st.button(
            "VPN: Secure Tunnel Connection\nResolve timeout and authentication session drops",
            key="card_vpn",
            use_container_width=True,
        ):
            selected_quick_prompt = "My VPN is disconnecting and failing to authenticate."
        if st.button(
            "SOFTWARE: Workplace App Crash\nRemediate unresponsive workplace software",
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
            <span class="status-pulse"></span>
            <span>IT support ready</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar=USER_AVATAR if message["role"] == "user" else ASSISTANT_AVATAR):
        st.markdown(message["content"])

show_resolution_feedback()

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

    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(active_prompt)

    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        requested_at = datetime.now(UTC).isoformat()
        request_started = perf_counter()
        outcome = "agent_success"
        error_stage = None
        error_type = None
        category = None
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

        except Exception as error:
            outcome = "fallback"
            error_stage = "foundry_agent_run"
            error_type = type(error).__name__
            st.markdown(
                """
                <div class="diagnostic-banner">
                    <span class="diagnostic-badge">LOCAL DIAGNOSTIC MODE</span>
                    <span>Microsoft Foundry unreachable &bull; First-line resolution guidance active</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            answer, category = local_troubleshooting_response(active_prompt)

        request_id = None
        try:
            request_id = TELEMETRY.record_request(
                conversation_id=conversation_id,
                requested_at=requested_at,
                latency_ms=round((perf_counter() - request_started) * 1000),
                outcome=outcome,
                error_stage=error_stage,
                error_type=error_type,
                category=category,
            )
        except Exception:
            # Analytics must never interrupt IT support or alter its fallback behavior.
            pass
        else:
            st.session_state.pending_feedback_request_id = request_id

        st.markdown(answer)

        assistant_message = STORE.append_message(
            conversation_id,
            "assistant",
            answer,
        )
        st.session_state.messages.append(assistant_message)

    st.rerun()
