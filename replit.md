# Teams Knowledge Base

## Overview
A multi-tenant knowledge base application integrating with Microsoft Teams and Azure DevOps. It extracts and indexes conversations, work items, and meeting transcripts into a PostgreSQL + pgvector database, offering AI-powered Q&A. The project emphasizes multi-tenancy, per-tenant data isolation, and configurable background data ingestion.

## User Preferences
- Prefers NestJS with TypeORM and repository pattern for backend
- Wants SOLID principles and service isolation
- Prefers clean, modern UI with shadcn/ui
- Table names must be singular
- All secrets must be stored encrypted with update timestamps
- No frontend changes unless explicitly specified

## System Architecture
The application uses a microservices architecture:
-   **Frontend**: Next.js 14 with shadcn/ui for a modern user interface.
-   **Management API**: NestJS (TypeScript) with TypeORM handles authentication, project management, connectors, data sources, and synchronization. It enforces multi-tenancy and encrypts sensitive configurations.
-   **AI Service**: FastAPI (Python) manages Teams and Azure DevOps API interactions, vector operations, and AI Q&A functionalities. It includes a thread-aware ingestion pipeline for Teams messages.
-   **Proxy**: A Python-based reverse proxy routes traffic to the respective services.
-   **Database**: PostgreSQL with pgvector for storing data and embeddings, supporting multi-tenancy with tenant-scoped data isolation.

**Data Hierarchy**:
-   **Connector**: Top-level configuration for external services (e.g., Microsoft Teams, Azure DevOps) storing encrypted credentials.
-   **Data Source**: Represents individual syncable segments within a connector (e.g., a Teams channel, a DevOps project) with specific sync settings.
-   **Semantic Data**: Generic indexed content from various sources, stored with embeddings for AI Q&A.

**Technical Implementations**:
-   **Authentication**: JWT strategy with Passport, bcrypt hashing, and `JwtAuthGuard`.
-   **Validation**: DTOs with `class-validator` and a global `ValidationPipe`.
-   **Secret Management**: AES-256-GCM encryption for sensitive configuration fields, with keys derived from `SESSION_SECRET`.
-   **Teams Ingestion**: A 5-stage pipeline for Teams messages: audit, meeting/chat split, thread grouping, content collection/clarification (using `gpt-4o-mini`), and embedding/storage.
-   **Azure DevOps Ingestion**: Fetches work items and comments, indexing them as searchable content.
-   **Work Item Hierarchy**: AI extracts `item_type` (Bug/Task/Issue) and `assigned_to` per item. When a thread yields 2+ items, code auto-creates a parent `UserStory` and stores all items as children via `parent_id`. Frontend renders UserStory cards with violet left border and children indented below.

## External Dependencies
-   **Database**: PostgreSQL with pgvector extension.
-   **Embeddings**: fastembed (BAAI/bge-small-en-v1.5) for local embedding generation.
-   **AI**: OpenAI via Replit AI Integrations for Q&A and content clarification.
-   **Microsoft Graph API**: For interacting with Microsoft Teams (channels, chats, messages, meeting transcripts). Requires specific Azure AD permissions.
-   **Azure DevOps REST API**: For interacting with Azure DevOps (work items, comments, iterations).
-   **Python Libraries**: `fastapi`, `uvicorn`, `psycopg2-binary`, `msal`, `openai`, `cryptography`, `pydub`, `requests`.
-   **Node.js Libraries**: `next`, `react`, `@radix-ui/*`, `tailwindcss`, `class-variance-authority`, `react-hook-form`, `zod`, `@nestjs/core`, `@nestjs/typeorm`, `typeorm`, `@nestjs/jwt`, `passport-jwt`, `bcryptjs`, `class-validator`, `pg`.