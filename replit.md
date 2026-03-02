# Teams Knowledge Base

## Overview
A multi-tenant knowledge base application that connects to Microsoft Teams via the Microsoft Graph API, extracts conversations from selected channels and group chats, indexes them in a PostgreSQL + pgvector database, and provides AI-powered Q&A. Features multi-tenancy with login/signup, per-tenant data isolation, and background data ingestion on configurable intervals.

## Architecture
- **Frontend**: Next.js 14 + shadcn/ui (port 5001, proxied through port 5000)
- **Management API**: NestJS with TypeORM (port 3001) — handles auth, projects, connectors, data sources, sync
- **AI Service**: FastAPI + Python (port 8001) — handles Teams API calls, vector operations, AI Q&A
- **Proxy**: Python reverse proxy on port 5000 routes traffic to all services
- **Database**: PostgreSQL + pgvector (Replit built-in)
- **Embeddings**: fastembed BAAI/bge-small-en-v1.5 (384 dimensions, local)
- **AI**: OpenAI via Replit AI Integrations

## Data Hierarchy
- **Connector**: Top-level connection config (e.g., Microsoft Teams with Azure AD credentials). Stores encrypted credentials.
- **Data Source**: Individual syncable segment under a connector (e.g., one Teams channel, one group chat). Has its own sync settings (interval, enabled, last_sync_at).
- One connector can have many data sources.

## Backend Architecture (NestJS)
Follows SOLID principles with clean separation of concerns:
- **Modules**: AuthModule, ProjectsModule, ConnectorsModule, DataSourcesModule, SyncModule, HealthModule, DatabaseModule
- **Pattern**: Controller → Service → Repository (TypeORM)
- **Auth**: JWT strategy with Passport, bcrypt password hashing, JwtAuthGuard
- **Validation**: DTOs with class-validator, global ValidationPipe
- **Tenant Isolation**: Every query scoped by tenant_id via repository pattern
- **Secret Encryption**: AES-256-GCM encryption for sensitive config fields (EncryptionService)
- **Credential Update Merge**: When updating connector credentials, empty fields are preserved from existing stored values

### Key Backend Files
- `backend/management/src/main.ts` — NestJS entry point (port 3001)
- `backend/management/src/app.module.ts` — Root module wiring all feature modules
- `backend/management/src/modules/auth/` — Auth module (signup, login, JWT strategy)
- `backend/management/src/modules/projects/` — Projects CRUD with tenant scoping
- `backend/management/src/modules/connectors/` — Connector CRUD with encrypted secrets, credential merge on update
- `backend/management/src/modules/datasources/` — Data sources management under connectors
- `backend/management/src/modules/sync/` — Sync history and status
- `backend/management/src/modules/database/entities/` — TypeORM entities (Tenant, User, Project, Connector, DataSource, SemanticData, SyncMetadata, SyncHistory)
- `backend/management/src/common/services/encryption.service.ts` — AES-256-GCM encryption/decryption for config secrets

### Key Frontend Files
- `frontend/src/app/dashboard/connectors/page.tsx` — Connectors management with expandable cards, inline data source management
- `frontend/src/app/` — Next.js pages (login, signup, dashboard tabs)
- `frontend/src/lib/api.ts` — API client with auth token management (connectors, dataSources, teams, ai, sync endpoints)
- `frontend/src/hooks/use-auth.tsx` — Auth context provider
- `frontend/src/hooks/use-project.tsx` — Project context provider

### AI Service Files
- `backend/ai-service/main.py` — FastAPI endpoints for Teams sync, search, Q&A (uses connector_id for credentials)
- `backend/ai-service/teams_client.py` — Microsoft Graph API client (with VTT attachment detection, meeting event detection, transcript fetch)
- `backend/ai-service/vector_ops.py` — pgvector operations with connector_id + data_source_id tracking
- `backend/ai-service/scheduler.py` — Background sync scheduler (iterates data_source rows, joins connector for credentials)
- `backend/ai-service/encryption.py` — Python decryption utility for encrypted configs
- `backend/ai-service/vtt_parser.py` — WebVTT parser (speaker extraction, timestamp parsing, segment grouping)
- `backend/ai-service/transcript_processor.py` — Orchestrates transcript ingestion from VTT attachments and meeting events

## Database Schema (all table names are singular)
- `tenant` — Multi-tenant organizations (id uuid, name, created_at)
- `user` — User accounts with tenant association (id uuid, email, password_hash, tenant_id)
- `project` — Project definitions with tenant isolation (id, name, description, tenant_id)
- `connector` — Connection configs per project (id, project_id, name, connector_type, config JSONB masked, encrypted_config JSONB encrypted, secrets_updated_at, tenant_id)
- `data_source` — Individual syncable segments under a connector (id, connector_id, project_id, tenant_id, name, source_type, config JSONB, sync_interval_minutes, sync_enabled, last_sync_at)
- `semantic_data` — Generic indexed content (id, tenant_id, project_id, connector_id, data_source_id, source_type, segment_type, source_identifier JSONB, content, embedding vector(384), sender, message_type)
- `sync_history` — Sync operation history (id uuid, tenant_id, project_id, connector_id, data_source_id, source_type, segment_type, status, records_added, records_fetched, error_message)

### Source Types & Segments
- **microsoft_teams**: team_channel, group_chat
- Source identifier is JSONB — flexible for any source: `{team_id, team_name, channel_id, channel_name}` or `{chat_id, chat_name}`

### Secret Encryption
- Sensitive config fields (client_secret, api_key, password, token, secret) are encrypted with AES-256-GCM
- Key derived from SESSION_SECRET via PBKDF2 (100,000 iterations, SHA-256)
- Encrypted values stored in `connector.encrypted_config` as `{__encrypted: true, value: "base64..."}`
- Plain `connector.config` stores masked values only (••••••••)
- `secrets_updated_at` tracks when secrets were last created/updated
- Both NestJS (encryption.service.ts) and Python AI service (encryption.py) can encrypt/decrypt

## Configuration
- Proxy routes: `/api/management/*` → port 3001, `/api/ai/*` → port 8001, all else → port 5001 (Next.js)
- Startup: `start.sh` launches NestJS (3001), AI service (8001), Next.js (5001), then runs `proxy.py` on port 5000
- `proxy.py` is a standalone threaded Python HTTP reverse proxy (no Streamlit dependency)
- JWT secret: SESSION_SECRET environment variable (required)
- Azure AD credentials stored encrypted per connector in connector.encrypted_config JSONB

## Required Azure AD Permissions
- `Team.ReadBasic.All`, `Channel.ReadBasic.All`, `ChannelMessage.Read.All`
- `Chat.Read.All` (for group chats), `User.Read.All` (for user discovery)
- `OnlineMeetingTranscript.Read.All` (optional, for auto-fetching Teams meeting transcripts — requires admin policy)

## Transcript Ingestion
Two transcript sources are supported during sync:
1. **VTT file attachments**: Any `.vtt` file shared in a chat or channel is auto-detected, downloaded, parsed, and indexed
2. **Teams meeting events**: Meeting recording/transcription events are detected; transcript content is fetched via Graph API (requires `OnlineMeetingTranscript.Read.All` — gracefully skipped if unavailable)
- VTT parsing handles `<v Speaker>` tags, `Speaker: text` prefixes, and standard WebVTT cue blocks
- Consecutive segments by the same speaker are grouped (up to ~500 chars) for embedding quality
- Transcript entries stored with `message_type: "transcript"` in semantic_data

## Dependencies
- **Backend (NestJS)**: @nestjs/core, @nestjs/typeorm, typeorm, @nestjs/jwt, passport-jwt, bcryptjs, class-validator, pg
- **AI Service (Python)**: fastapi, uvicorn, psycopg2-binary, msal, fastembed, openai, cryptography
- **Frontend**: next, react, @radix-ui/*, tailwindcss, class-variance-authority, react-hook-form, zod

## Recent Changes
- 2026-02-23: Restructured to two-level hierarchy: Connector (credentials) → Data Source (individual channels/chats with sync settings)
- 2026-02-23: Built Connectors page with expandable cards, inline data source management (add channels/group chats)
- 2026-02-23: Added credential merge on update — empty fields preserved from existing stored values
- 2026-02-23: Old pages (data-sources, channels, group-chats) redirect to /dashboard/connectors
- 2026-02-23: Updated AI service scheduler to iterate individual data_source rows for sync
- 2026-03-02: Eliminated sync_metadata table — consolidated sync checkpoint into data_source.last_sync_at
- 2026-03-02: Added manual "Sync Now" button per data source on Connectors page
- 2026-03-02: Fixed sync scheduler to validate credentials before attempting sync (skips invalid connectors)
- 2026-03-02: Fixed Knowledge Base sync history table to show correct fields, status badges, and error messages
- 2026-03-02: Added meeting transcript ingestion — auto-detects VTT file attachments and Teams meeting recording events during sync
- 2026-03-02: Created VTT parser (vtt_parser.py) with speaker extraction, timestamp parsing, and segment grouping for quality embeddings
- 2026-03-02: Added transcript_processor.py to orchestrate VTT download + parsing + meeting transcript fetch from Graph API
- 2026-02-23: Renamed all tables to singular (tenant, user, project, connector, data_source, semantic_data, sync_history)
- 2026-02-23: Added AES-256-GCM encryption for connector secrets with secrets_updated_at tracking
- 2026-02-23: Replaced teams_messages with generic semantic_data table (source_type, segment_type, source_identifier JSONB)
- 2026-02-23: Rebuilt management API with NestJS, TypeORM, repository pattern, SOLID principles
- 2026-02-23: Added multi-tenancy with JWT auth, signup/login, tenant-scoped data isolation
- 2026-02-23: Removed Streamlit dependency entirely; app.py is now a plain Python launcher for start.sh
- 2026-02-23: Replaced Streamlit frontend with Next.js + shadcn/ui
- 2026-02-22: Added multi-project support with pluggable data source architecture
- 2026-02-22: Migrated vector store from ChromaDB to PostgreSQL + pgvector

## User Preferences
- Prefers NestJS with TypeORM and repository pattern for backend
- Wants SOLID principles and service isolation
- Prefers clean, modern UI with shadcn/ui
- Table names must be singular
- All secrets must be stored encrypted with update timestamps
- No frontend changes unless explicitly specified
