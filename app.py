import asyncio
import os

import streamlit as st
from agent_framework.foundry import FoundryAgent
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv


load_dotenv()

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
AGENT_NAME = "IT-Helpdesk-Agent"
AGENT_VERSION = os.getenv("FOUNDRY_AGENT_VERSION") or None


async def get_agent_response(prompt, session):
    """Run the existing service-managed Prompt Agent."""
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


st.set_page_config(page_title="IT Helpdesk", page_icon="🛠️", layout="centered")

st.markdown(
    """
    <style>
        html, body, [data-testid="stAppViewContainer"], .stApp { background: #f7f9fc !important; color: #1d2939 !important; }
        [data-testid="stMainBlockContainer"] { max-width: 920px; padding: 3rem 1rem 5.25rem !important; }
        .helpdesk-header { margin-bottom: 1rem; }
        [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 0.75rem !important; }
        [data-testid="stHorizontalBlock"] > div { min-width: 0 !important; }
        .helpdesk-title { color: #172033 !important; font-size: 2rem; font-weight: 700; letter-spacing: -0.035em; margin: 0; }
        .helpdesk-subtitle { color: #667085 !important; font-size: 1rem; margin: 0.35rem 0 0; }
        .connection-status { align-items: center; color: #18794e !important; display: flex; font-size: 0.82rem; font-weight: 600; gap: 0.45rem; margin-top: 0.65rem; }
        .connection-status::before { background: #22a06b; border-radius: 50%; content: ""; height: 0.5rem; width: 0.5rem; }
        [data-testid="stChatMessage"] { background: #ffffff !important; border: 1px solid #e7ebf2; border-radius: 12px; box-shadow: none; color: #1d2939 !important; margin: 0.5rem 0 !important; min-height: 0 !important; padding: 0.45rem 0.7rem !important; }
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { background: #eaf3ff !important; border-color: #cfe3ff; }
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"], [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] * { color: #1d2939 !important; }
        [data-testid="stChatMessage"] p { line-height: 1.5; margin: 0 !important; }
        section[data-testid="stAppScrollToBottomContainer"], [data-testid="stBottom"] { background: #f7f9fc !important; }
        [data-testid="stBottom"] { border-top: 1px solid #e7ebf2; padding: 0.45rem 0 0.55rem !important; }
        [data-testid="stBottom"] > div { background: #f7f9fc !important; }
        [data-testid="stChatInput"], [data-testid="stChatInput"] > div { background: #ffffff !important; border-color: #cfd8e3 !important; border-radius: 10px !important; }
        [data-testid="stChatInput"] textarea { background: #ffffff !important; color: #1d2939 !important; font-size: 0.95rem; line-height: 1.4; min-height: 1.25rem !important; }
        [data-testid="stChatInput"] textarea::placeholder { color: #667085 !important; }
        .stButton > button { background: #ffffff; border: 1px solid #d0d5dd; border-radius: 8px; color: #344054; font-size: 0.85rem; font-weight: 600; padding: 0.4rem 0.8rem; }
        .stButton > button:hover { background: #f9fafb; border-color: #98a2b3; color: #1d2939; }
        @media (max-width: 420px) {
            [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
            [data-testid="stHorizontalBlock"] > div { min-width: calc(100% - 24px) !important; }
        }
    </style>
    """,
    unsafe_allow_html=True,
)

header, action = st.columns([3, 1], vertical_alignment="top")
with header:
    st.markdown(
        """
        <div class="helpdesk-header">
            <p class="helpdesk-title">IT Helpdesk</p>
            <p class="helpdesk-subtitle">AI-powered first-level IT support</p>
            <div class="connection-status">Connected to Microsoft Foundry</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with action:
    clear_conversation = st.button("New conversation")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "agent_session" not in st.session_state:
    st.session_state.agent_session = None

if clear_conversation:
    st.session_state.messages = []
    st.session_state.agent_session = None
    st.rerun()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Describe your IT issue"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            answer, st.session_state.agent_session = asyncio.run(
                get_agent_response(prompt, st.session_state.agent_session)
            )
            st.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})
        except Exception as error:
            st.error(f"Could not reach the helpdesk agent: {error}")
