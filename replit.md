# Teams Knowledge Base

## Overview
A multi-tenant knowledge base application that connects to Microsoft Teams via the Microsoft Graph API, extracts conversations from selected channels and group chats, indexes them in a PostgreSQL + pgvector database, and provides AI-powered Q&A. Features multi-tenancy with login/signup, per-tenant data isolation, and background data ingestion on configurable intervals.

## Architecture
- **Frontend**: Next.js 14 + shadcn/ui (port 5001, proxied through port 5000)
- **Management API**: NestJS with TypeORM (port 3001) — handles auth, projects, data sources, sync
- **AI Service**: FastAPI + Python (port 8001) — handles Teams API calls, vector operations, AI Q&A
- **Proxy**: Python reverse proxy on port 5000 routes traffic to all services
- **Database**: PostgreSQL + pgvector (Replit built-in)
- **Embeddings**: fastembed BAAI/bge-small-en-v1.5 (384 dimensions, local)
- **AI**: OpenAI via Replit AI Integrations

## Backend Architecture (NestJS)
Follows SOLID principles with clean separation of concerns:
- **Modules**: AuthModule, ProjectsModule, DataSourcesModule, SyncModule, HealthModule, DatabaseModule
- **Pattern**: Controller → Service → Repository (TypeORM)
- **Auth**: JWT strategy with Passport, bcrypt password hashing, JwtAuthGuard
- **Validation**: DTOs with class-validator, global ValidationPipe
- **Tenant Isolation**: Every query scoped by tenant_id via repository pattern

### Key Backend Files
- `backend/management/src/main.ts` — NestJS entry point (port 3001)
- `backend/management/src/app.module.ts` — Root module wiring all feature modules
- `backend/management/src/modules/auth/` — Auth module (signup, login, JWT strategy)
- `backend/management/src/modules/projects/` — Projects CRUD with tenant scoping
- `backend/management/src/modules/datasources/` — Data sources management
- `backend/management/src/modules/sync/` — Sync history and status
- `backend/management/src/modules/database/entities/` — TypeORM entities (Tenant, User, Project, etc.)
- `backend/management/src/common/` — Shared guards, decorators, interfaces

### Key Frontend Files
- `frontend/src/app/` — Next.js pages (login, signup, dashboard tabs)
- `frontend/src/lib/api.ts` — API client with auth token management
- `frontend/src/hooks/use-auth.tsx` — Auth context provider

### AI Service Files
- `backend/ai-service/main.py` — FastAPI endpoints for Teams sync, search, Q&A
- `backend/ai-service/teams_client.py` — Microsoft Graph API client
- `backend/ai-service/vector_ops.py` — pgvector operations
- `backend/ai-service/scheduler.py` — Background sync scheduler

## Database Schema
- `tenants` — Multi-tenant organizations (id uuid, name, created_at)
- `users` — User accounts with tenant association (id uuid, email, password_hash, tenant_id)
- `projects` — Project definitions with tenant isolation (id, name, description, tenant_id)
- `project_data_sources` — Data source configs per project (id, project_id, source_type, config JSONB, tenant_id)
- `teams_messages` — Message content with vector embeddings (id, content, embedding vector(384), tenant_id)
- `sync_metadata` — Last sync time tracking per channel/project
- `sync_history` — Sync operation history with status/counts

## Configuration
- Proxy routes: `/api/management/*` → port 3001, `/api/ai/*` → port 8001, all else → port 5001 (Next.js)
- Startup: Modified streamlit wrapper starts all services then execs into proxy on port 5000
- JWT secret: SESSION_SECRET environment variable (required)
- Azure AD credentials stored per data source in project_data_sources.config JSONB

## Required Azure AD Permissions
- `Team.ReadBasic.All`, `Channel.ReadBasic.All`, `ChannelMessage.Read.All`
- `Chat.Read.All` (for group chats), `User.Read.All` (for user discovery)

## Dependencies
- **Backend (NestJS)**: @nestjs/core, @nestjs/typeorm, typeorm, @nestjs/jwt, passport-jwt, bcryptjs, class-validator, pg
- **AI Service (Python)**: fastapi, uvicorn, psycopg2-binary, msal, fastembed, openai
- **Frontend**: next, react, @radix-ui/*, tailwindcss, class-variance-authority

## Recent Changes
- 2026-02-23: Rebuilt management API with NestJS, TypeORM, repository pattern, SOLID principles
- 2026-02-23: Added multi-tenancy with JWT auth, signup/login, tenant-scoped data isolation
- 2026-02-23: Replaced Streamlit frontend with Next.js + shadcn/ui
- 2026-02-22: Added multi-project support with pluggable data source architecture
- 2026-02-22: Migrated vector store from ChromaDB to PostgreSQL + pgvector

## User Preferences
- Prefers NestJS with TypeORM and repository pattern for backend
- Wants SOLID principles and service isolation
- Prefers clean, modern UI with shadcn/ui
