# Teams Knowledge Base

## Overview
A multi-project Streamlit application that connects to Microsoft Teams via the Microsoft Graph API, extracts conversations from selected channels and group chats, indexes them in a PostgreSQL + pgvector database, and provides AI-powered Q&A scoped per project. Designed as a foundation for a multi-agent system with pluggable data sources.

## Architecture
- **Frontend**: Streamlit (port 5000)
- **Project System**: Multi-project support with per-project data isolation and pluggable data sources
- **Teams Integration**: Microsoft Graph API via MSAL (application-level auth)
- **Vector Database**: PostgreSQL + pgvector (cloud-hosted, Replit built-in database)
- **Embeddings**: fastembed BAAI/bge-small-en-v1.5 (384 dimensions, runs locally, no API key needed)
- **AI**: OpenAI via Replit AI Integrations (GPT-5.2 for Q&A)

## Key Files
- `app.py` — Main Streamlit application with UI tabs (Projects, Data Sources, Channels, Group Chats, Knowledge Base, Ask Questions)
- `teams_client.py` — Microsoft Graph API client for fetching teams, channels, group chats, and messages
- `vector_store.py` — PostgreSQL + pgvector wrapper with project-scoped operations for storing, searching, and managing indexed messages
- `ai_assistant.py` — OpenAI-powered Q&A and summarization using Replit AI Integrations

## Database Schema
- `projects` — Stores project definitions (id, name, description, created_at)
- `project_data_sources` — Links data sources to projects (id, project_id, source_type, config JSONB)
- `teams_messages` — Stores message content with vector embeddings (id, content, embedding vector(384), sender, team, channel, project_id, etc.)
- `sync_metadata` — Tracks last sync time per team/channel/project combination

## Configuration
- `.streamlit/config.toml` — Streamlit server config (port 5000, headless)
- Azure AD credentials stored as secrets (AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID)
- DATABASE_URL — PostgreSQL connection string (auto-provided by Replit)

## Required Azure AD Permissions
- `Team.ReadBasic.All`
- `Channel.ReadBasic.All`
- `ChannelMessage.Read.All`
- `Chat.Read.All` (for group chats access)
- `User.Read.All` (for listing users to discover group chats)

## Dependencies
- streamlit, msal, psycopg2-binary, requests, tenacity, pandas, openai, fastembed

## Recent Changes
- 2026-02-22: Added multi-project support with per-project data isolation and pluggable data source architecture
- 2026-02-22: Replaced M365 Groups with Teams group chats syncing (multi-person chat conversations)
- 2026-02-22: Switched embeddings from OpenAI API to fastembed (local, no API key needed)
- 2026-02-22: Migrated vector store from ChromaDB (local) to PostgreSQL + pgvector (cloud)
- 2026-02-22: Fixed thread reply syncing — replies to older threads now captured properly
- 2026-02-22: Initial build with Teams connection, channel sync, vector indexing, and AI Q&A
