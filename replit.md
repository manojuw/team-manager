# Teams Knowledge Base

## Overview
A Streamlit application that connects to Microsoft Teams via the Microsoft Graph API, extracts conversations from selected channels, indexes them in a ChromaDB vector database, and provides AI-powered Q&A about project discussions, requirements, and team member commitments.

## Architecture
- **Frontend**: Streamlit (port 5000)
- **Teams Integration**: Microsoft Graph API via MSAL (application-level auth)
- **Vector Database**: ChromaDB (persistent local storage in `./chroma_data/`)
- **AI**: OpenAI via Replit AI Integrations (GPT-5.2 for Q&A)

## Key Files
- `app.py` — Main Streamlit application with UI tabs (Channel Selector, Knowledge Base, Ask Questions)
- `teams_client.py` — Microsoft Graph API client for fetching teams, channels, and messages
- `vector_store.py` — ChromaDB wrapper for storing, searching, and managing indexed messages
- `ai_assistant.py` — OpenAI-powered Q&A and summarization using Replit AI Integrations

## Configuration
- `.streamlit/config.toml` — Streamlit server config (port 5000, headless)
- Azure AD credentials entered via UI (Client ID, Client Secret, Tenant ID)

## Required Azure AD Permissions
- `Team.ReadBasic.All`
- `Channel.ReadBasic.All`
- `ChannelMessage.Read.All`
- `Group.Read.All`

## Dependencies
- streamlit, msal, chromadb, requests, tenacity, pandas, openai

## Recent Changes
- 2026-02-22: Initial build with Teams connection, channel sync, vector indexing, and AI Q&A
