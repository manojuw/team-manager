# Teams Knowledge Base

## Overview
A Streamlit application that connects to Microsoft Teams via the Microsoft Graph API, extracts conversations from selected channels, indexes them in a PostgreSQL + pgvector database, and provides AI-powered Q&A about project discussions, requirements, and team member commitments.

## Architecture
- **Frontend**: Streamlit (port 5000)
- **Teams Integration**: Microsoft Graph API via MSAL (application-level auth)
- **Vector Database**: PostgreSQL + pgvector (cloud-hosted, Replit built-in database)
- **Embeddings**: fastembed BAAI/bge-small-en-v1.5 (384 dimensions, runs locally, no API key needed)
- **AI**: OpenAI via Replit AI Integrations (GPT-5.2 for Q&A)

## Key Files
- `app.py` — Main Streamlit application with UI tabs (Channel Selector, Group Selector, Knowledge Base, Ask Questions)
- `teams_client.py` — Microsoft Graph API client for fetching teams, channels, groups, and messages
- `vector_store.py` — PostgreSQL + pgvector wrapper for storing, searching, and managing indexed messages with fastembed local embeddings
- `ai_assistant.py` — OpenAI-powered Q&A and summarization using Replit AI Integrations

## Database Schema
- `teams_messages` — Stores message content with vector embeddings (id, content, embedding vector(384), sender, team, channel, etc.)
- `sync_metadata` — Tracks last sync time per team/channel pair

## Configuration
- `.streamlit/config.toml` — Streamlit server config (port 5000, headless)
- Azure AD credentials stored as secrets (AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID)
- DATABASE_URL — PostgreSQL connection string (auto-provided by Replit)

## Required Azure AD Permissions
- `Team.ReadBasic.All`
- `Channel.ReadBasic.All`
- `ChannelMessage.Read.All`
- `Group.Read.All`
- `Group.ReadWrite.All` (for group conversations access)

## Dependencies
- streamlit, msal, psycopg2-binary, requests, tenacity, pandas, openai, fastembed

## Recent Changes
- 2026-02-22: Added Microsoft 365 Group conversations syncing alongside Teams channels
- 2026-02-22: Switched embeddings from OpenAI API to fastembed (local, no API key needed)
- 2026-02-22: Migrated vector store from ChromaDB (local) to PostgreSQL + pgvector (cloud)
- 2026-02-22: Fixed thread reply syncing — replies to older threads now captured properly
- 2026-02-22: Initial build with Teams connection, channel sync, vector indexing, and AI Q&A
