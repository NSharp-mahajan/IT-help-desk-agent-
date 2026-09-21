# IT Helpdesk Agent

An AI-powered first-level IT support chat application built with Streamlit and Microsoft Foundry.

## Overview

The IT Helpdesk Agent gives users a conversational way to describe common technical issues and receive troubleshooting guidance. Streamlit provides the chat experience, while a service-managed Microsoft Foundry agent processes the request and returns a response using its configured instructions and knowledge sources.

The project is designed to reduce repetitive first-line support work by helping users find relevant troubleshooting steps before an issue needs human escalation.

## System Workflow

```mermaid
flowchart LR
    U[User] --> UI[Streamlit UI]
    UI --> FA[Microsoft Foundry Agent]
    FA --> C[Issue categorization]
    C --> R[File Search / RAG]
    R --> KB[IT Knowledge Base]
    KB --> T[Troubleshooting response]
    T --> D{Resolved?}
    D -->|Yes| S[User applies solution]
    D -->|No| E[Escalation guidance]
```

In this repository, the application sends the user's prompt and the current agent session to `IT-Helpdesk-Agent`. Categorization and retrieval are responsibilities of the Foundry agent configuration and its connected knowledge sources; they are not implemented as separate local Python modules.

## Architecture

```mermaid
flowchart TB
    subgraph Client[User-facing application]
        ST[Streamlit chat UI\nconversation history and reset]
    end

    subgraph Foundry[Microsoft Foundry service]
        AG[IT-Helpdesk-Agent\nservice-managed Prompt Agent]
        CAT[Category routing]
        FS[File Search / RAG]
    end

    KB[IT Knowledge Base\nFoundry-connected source]
    AUTH[DefaultAzureCredential]

    ST -->|Prompt and session| AG
    AUTH -->|Azure authentication| AG
    AG --> CAT --> FS --> KB
    KB -->|Relevant support context| AG
    AG -->|Answer| ST
```

- **Streamlit** renders the chat interface, stores messages in session state, and starts a new conversation when requested.
- **Microsoft Foundry** hosts the existing `IT-Helpdesk-Agent` and handles the service-managed agent run.
- **File Search / RAG** represents retrieval configured for the Foundry agent. The repository does not contain a local retrieval pipeline.
- **IT Knowledge Base** is the support material connected to the agent configuration. No knowledge-base files or database are stored in this repository.

## Key Features

- Conversational IT support through a Streamlit chat interface
- Persistent conversation messages during the current Streamlit session
- New conversation control that clears the current messages and agent session
- Microsoft Foundry agent integration using the configured project endpoint
- Azure authentication through `DefaultAzureCredential`
- User-visible error handling when the helpdesk agent cannot be reached

## Supported IT Categories

- Wi-Fi / Network
- VPN
- Password / Account
- Printer
- Email
- Software Installation

These categories describe the intended first-level support scope. The repository does not contain a separate local category-classification model.

## Tech Stack

- Python
- Streamlit
- Microsoft Foundry Agent Framework
- Azure Identity
- `python-dotenv`
- `unittest` and Python AST parsing for the smoke test

## Knowledge Base

The application is prepared to work with knowledge sources connected to the Microsoft Foundry agent, including a File Search / RAG workflow. The actual knowledge-base content and retrieval configuration are managed outside this repository and are not embedded in `app.py`.

## Project Structure

```text
.
├── app.py             # Streamlit UI and Foundry agent integration
├── requirements.txt   # Python dependencies
├── test_app.py        # Application smoke test
└── .env               # Local configuration; do not commit secrets
```

## Setup and Run

1. Create and activate a Python virtual environment.

   ```bash
   python -m venv .venv
   ```

   On Windows:

   ```powershell
   .venv\Scripts\Activate.ps1
   ```

2. Install the dependencies.

   ```bash
   pip install -r requirements.txt
   ```

3. Create a local `.env` file with the Foundry project endpoint. Do not commit the file or its values.

   ```env
   FOUNDRY_PROJECT_ENDPOINT=<your-foundry-project-endpoint>
   FOUNDRY_AGENT_VERSION=<optional-agent-version>
   ```

4. Ensure `DefaultAzureCredential` can authenticate with Azure in your development environment.

5. Start the application.

   ```bash
   streamlit run app.py
   ```

6. Run the smoke test when needed.

   ```bash
   python -m unittest test_app.py
   ```

## Example User Queries

- “My laptop can see the Wi-Fi network, but it cannot connect.”
- “How do I connect to the company VPN?”
- “I am locked out of my account and need to reset my password.”
- “The printer is online, but my document is stuck in the queue.”
- “I am not receiving new work emails.”
- “How can I install the approved PDF reader?”

## Current Limitations

- Automatic ticket creation is **not implemented**.
- MCP integration is **not implemented**.
- There is no local database or ticket history.
- There is no authentication UI in the application.
- Cloud deployment is not included in this repository.
- The local application does not implement its own File Search / RAG pipeline or knowledge-base management.
- Escalation currently means guidance in the agent response; it does not create or route a support ticket.

## Future Scope

- Add ticket creation and escalation through an approved service or MCP integration.
- Add authenticated user and support-agent views.
- Add structured issue metadata and ticket history storage.
- Expand and version the IT knowledge base with retrieval evaluation.
- Add monitoring, feedback collection, and response-quality metrics.
- Deploy the Streamlit application and Foundry configuration through a documented release process.

## Team / Academic Project Note

This repository is an academic and portfolio-oriented project demonstrating a practical IT support workflow with Streamlit and Microsoft Foundry. Team members can extend the Foundry agent configuration, knowledge sources, evaluation tests, and future ticketing integrations without exposing credentials in source control.