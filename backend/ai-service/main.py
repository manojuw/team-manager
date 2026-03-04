import os
import logging
import hashlib
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import psycopg2
import psycopg2.extras
import requests
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import jwt

import re as re_module
import uuid as _uuid
from teams_client import TeamsClient
from vector_ops import VectorOps
from ai_ops import ask_question_ai, summarize_ai
from scheduler import SyncScheduler
from encryption import decrypt_config
from azure_devops_client import AzureDevOpsClient, DevOpsApiError
from devops_sync import fetch_devops_work_items_as_messages
from thread_engine import ThreadEngine, _parse_dt
from message_processor import MessageProcessor
from audio_processor import AudioProcessor
from work_item_extractor import WorkItemExtractor
from work_item_search import WorkItemSearch
from openai import OpenAI as _OpenAI

_audio_processor = AudioProcessor()


def _make_openai_client():
    api_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return _OpenAI(**kwargs)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
JWT_SECRET = os.environ.get("SESSION_SECRET", "fallback-secret-key")

scheduler = SyncScheduler()


def _run_migrations():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE thread_message
                  ADD COLUMN IF NOT EXISTS is_work_item_related BOOLEAN DEFAULT FALSE
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS suggested_work_item (
                  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  tenant_id         UUID NOT NULL,
                  project_id        VARCHAR NOT NULL,
                  connector_id      UUID,
                  data_source_id    UUID,
                  thread_id         UUID,
                  title             TEXT NOT NULL,
                  description       TEXT,
                  status            VARCHAR(50) DEFAULT 'pending',
                  source_message_ids TEXT[],
                  embedding         vector(1536),
                  created_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_suggested_wi_thread
                  ON suggested_work_item(thread_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_suggested_wi_tenant
                  ON suggested_work_item(tenant_id, project_id)
            """)
            cur.execute("""
                ALTER TABLE suggested_work_item
                  ADD COLUMN IF NOT EXISTS semantic_data_id UUID
            """)
        conn.commit()
        conn.close()
        logger.info("[Migration] Migrations applied successfully")
    except Exception as e:
        logger.error(f"[Migration] Migration failed: {e}")


def _retro_match_work_items():
    from vector_ops import _expand_queries_for_devops_match, _confirm_devops_match_with_gpt
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, title, description, tenant_id::text, project_id
                   FROM suggested_work_item
                   WHERE semantic_data_id IS NULL AND embedding IS NOT NULL"""
            )
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        logger.error(f"[RetroMatch] Failed to fetch suggested work items: {e}")
        return

    if not rows:
        logger.info("[RetroMatch] No suggested work items need retro-matching")
        return

    logger.info(f"[RetroMatch] Checking {len(rows)} suggested work items with no DevOps link")
    openai_client = _make_openai_client()
    matched = 0

    for row in rows:
        item_id, title, description, tenant_id, project_id = row
        desc = description or ""
        try:
            queries = _expand_queries_for_devops_match(openai_client, title, desc)
            candidates = vector_ops.search_devops_candidates(queries, tenant_id, project_id, n_results=5)
            linked = None
            for cand in candidates:
                if cand["sim"] >= 0.35:
                    confirmed = _confirm_devops_match_with_gpt(
                        openai_client, title, desc, cand["content"]
                    )
                    if confirmed:
                        linked = cand["id"]
                        break
            if linked:
                conn = psycopg2.connect(DATABASE_URL)
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE suggested_work_item SET semantic_data_id = %s WHERE id = %s",
                        (linked, item_id),
                    )
                conn.commit()
                conn.close()
                logger.info(f"[RetroMatch] '{title}' → linked to DevOps {linked}")
                matched += 1
            else:
                logger.info(f"[RetroMatch] '{title}' → no match found")
        except Exception as e:
            logger.error(f"[RetroMatch] Error processing '{title}': {e}")

    logger.info(f"[RetroMatch] Complete: {matched}/{len(rows)} items linked")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _run_migrations()
    _retro_match_work_items()
    scheduler.start()
    logger.info("Background sync scheduler started")
    yield
    scheduler.stop()
    logger.info("Background sync scheduler stopped")


app = FastAPI(title="AI Service", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

vector_ops = VectorOps()


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


def verify_token(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth header")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


class SyncChannelRequest(BaseModel):
    project_id: str
    connector_id: str
    data_source_id: Optional[str] = None
    team_id: str
    team_name: str
    channel_id: str
    channel_name: str


class SyncGroupChatRequest(BaseModel):
    project_id: str
    connector_id: str
    data_source_id: Optional[str] = None
    chat_id: str
    chat_name: str


class SearchRequest(BaseModel):
    project_id: str
    query: str
    n_results: int = 20
    filter_team: Optional[str] = None
    filter_channel: Optional[str] = None
    filter_sender: Optional[str] = None


class AskRequest(BaseModel):
    project_id: str
    question: str
    chat_history: list = []
    filter_team: Optional[str] = None
    filter_channel: Optional[str] = None


class SummarizeRequest(BaseModel):
    project_id: str


class ListTeamsRequest(BaseModel):
    connector_id: str


class ListChannelsRequest(BaseModel):
    connector_id: str
    team_id: str


class ListUsersRequest(BaseModel):
    connector_id: str


class ListGroupChatsRequest(BaseModel):
    connector_id: str
    user_ids: list[str]


class ListDevOpsProjectsRequest(BaseModel):
    connector_id: str


class ListDevOpsIterationsRequest(BaseModel):
    connector_id: str
    devops_project: str


class SyncDevOpsProjectRequest(BaseModel):
    project_id: str
    connector_id: str
    data_source_id: Optional[str] = None
    devops_project_name: str
    devops_project_id: Optional[str] = None


def _get_connector_config(connector_id: str, tenant_id: str) -> dict:
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT config, encrypted_config FROM connector WHERE id = %s AND tenant_id = %s",
                (connector_id, tenant_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Connector not found")

            encrypted_config = row[1]
            if encrypted_config:
                if isinstance(encrypted_config, str):
                    encrypted_config = json.loads(encrypted_config)
                return decrypt_config(encrypted_config)

            config = row[0]
            if isinstance(config, str):
                config = json.loads(config)
            return config or {}
    finally:
        conn.close()


def _get_teams_client(connector_id: str, tenant_id: str) -> TeamsClient:
    config = _get_connector_config(connector_id, tenant_id)
    client_id = config.get("client_id", "")
    client_secret = config.get("client_secret", "")
    azure_tenant_id = config.get("tenant_id", "")
    if not all([client_id, client_secret, azure_tenant_id]):
        raise HTTPException(status_code=400, detail="Connector credentials not configured")
    return TeamsClient(client_id, client_secret, azure_tenant_id)


def _get_devops_client(connector_id: str, tenant_id: str) -> AzureDevOpsClient:
    config = _get_connector_config(connector_id, tenant_id)
    organization = config.get("organization", "")
    if not organization:
        raise HTTPException(status_code=400, detail="Azure DevOps organization not configured")
    auth_type = config.get("auth_type", "pat")
    if auth_type == "pat":
        pat = config.get("pat", "")
        if not pat:
            raise HTTPException(status_code=400, detail="Personal Access Token not configured")
        return AzureDevOpsClient(organization=organization, auth_type="pat", pat=pat)
    else:
        client_id = config.get("client_id", "")
        client_secret = config.get("client_secret", "")
        azure_tenant_id = config.get("tenant_id", "")
        if not all([client_id, client_secret, azure_tenant_id]):
            raise HTTPException(status_code=400, detail="Azure AD credentials not configured")
        return AzureDevOpsClient(
            organization=organization, auth_type="azure_ad",
            client_id=client_id, client_secret=client_secret, tenant_id=azure_tenant_id
        )


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "ai-service"}


@app.post("/api/teams/list-teams")
def list_teams(req: ListTeamsRequest, user=Depends(verify_token)):
    client = _get_teams_client(req.connector_id, user["tenantId"])
    teams = client.get_teams()
    return {"teams": teams}


@app.post("/api/teams/list-channels")
def list_channels(req: ListChannelsRequest, user=Depends(verify_token)):
    client = _get_teams_client(req.connector_id, user["tenantId"])
    channels = client.get_channels(req.team_id)
    return {"channels": channels}


@app.post("/api/teams/list-users")
def list_users(req: ListUsersRequest, user=Depends(verify_token)):
    client = _get_teams_client(req.connector_id, user["tenantId"])
    users = client.get_users()
    return {"users": users}


@app.post("/api/teams/list-group-chats")
def list_group_chats(req: ListGroupChatsRequest, user=Depends(verify_token)):
    client = _get_teams_client(req.connector_id, user["tenantId"])
    chats = client.get_group_chats(user_ids=req.user_ids)
    return {"chats": chats}


@app.post("/api/sync/channel")
def sync_channel(req: SyncChannelRequest, user=Depends(verify_token)):
    tenant_id = user["tenantId"]
    client = _get_teams_client(req.connector_id, tenant_id)

    source_identifier = {
        "team_id": req.team_id,
        "team_name": req.team_name,
        "channel_id": req.channel_id,
        "channel_name": req.channel_name,
    }

    last_sync = vector_ops.get_last_sync(req.data_source_id)
    since = None
    if last_sync != "Never":
        try:
            since = datetime.fromisoformat(last_sync)
        except (ValueError, TypeError):
            since = None

    messages = client.get_channel_messages(req.team_id, req.channel_id, since=since)

    vector_ops.insert_raw_messages(
        messages, "microsoft_teams", "team_channel",
        req.project_id, tenant_id, req.connector_id, req.data_source_id
    )

    meeting_messages = [m for m in messages if m.get("message_type") == "meeting_event"]
    chat_messages = [m for m in messages if m.get("message_type") != "meeting_event"]

    meeting_threads = [{
        "id": str(_uuid.uuid4()),
        "messages": [m],
        "participants": {m.get("sender", "Unknown")},
        "started_at": _parse_dt(m.get("created_at", "")),
        "last_message_at": _parse_dt(m.get("created_at", "")),
        "has_audio": False, "has_video": False, "is_meeting": True,
    } for m in meeting_messages]

    openai_client = _make_openai_client()
    thread_engine = ThreadEngine(time_window_minutes=60, lookback_count=10, openai_client=openai_client)
    chat_threads = thread_engine.group_messages(chat_messages)

    processor = MessageProcessor(openai_client=openai_client, audio_processor=_audio_processor, teams_client=client)
    processed_meeting = [r for r in (processor.process_thread(t) for t in meeting_threads) if r is not None]
    processed_chat = [r for r in (processor.process_thread(t) for t in chat_threads) if r is not None]

    meeting_added = vector_ops.add_threads(
        processed_meeting, "microsoft_teams", "meeting", source_identifier,
        req.project_id, tenant_id, req.connector_id, req.data_source_id
    )
    chat_added = vector_ops.add_threads(
        processed_chat, "microsoft_teams", "team_channel", source_identifier,
        req.project_id, tenant_id, req.connector_id, req.data_source_id
    )
    added = meeting_added + chat_added

    all_threads = meeting_threads + chat_threads
    for thread in all_threads:
        msg_ids = [m["id"] for m in thread.get("messages", []) if m.get("id")]
        if msg_ids:
            vector_ops.update_thread_message_thread_ids(
                thread["id"], msg_ids, req.connector_id, req.data_source_id
            )

    extractor = WorkItemExtractor(openai_client=openai_client)
    for pt in processed_chat + processed_meeting:
        work_items = extractor.analyze_thread(pt)
        if work_items:
            vector_ops.store_work_items(
                work_items, pt["id"],
                tenant_id, req.project_id, req.connector_id, req.data_source_id,
                openai_client=openai_client
            )

    _record_sync_history(tenant_id, req.project_id, req.connector_id, req.data_source_id,
                         added, len(messages), "microsoft_teams", "team_channel")

    if req.data_source_id:
        _update_data_source_last_sync(req.data_source_id)

    processed_threads = processed_meeting + processed_chat
    audio_count = sum(1 for t in processed_threads if t.get("has_audio"))
    video_count = sum(1 for t in processed_threads if t.get("has_video"))

    return {
        "added": added,
        "total_fetched": len(messages),
        "threads": len(processed_threads),
        "meeting_threads": len(processed_meeting),
        "chat_threads": len(processed_chat),
        "audio_transcribed": audio_count,
        "video_transcribed": video_count,
    }


@app.post("/api/sync/group-chat")
def sync_group_chat(req: SyncGroupChatRequest, user=Depends(verify_token)):
    tenant_id = user["tenantId"]
    client = _get_teams_client(req.connector_id, tenant_id)

    source_identifier = {
        "chat_id": req.chat_id,
        "chat_name": req.chat_name,
    }

    last_sync = vector_ops.get_last_sync(req.data_source_id)
    since = None
    if last_sync != "Never":
        try:
            since = datetime.fromisoformat(last_sync)
        except (ValueError, TypeError):
            since = None

    messages = client.get_chat_messages(req.chat_id, since=since)

    vector_ops.insert_raw_messages(
        messages, "microsoft_teams", "group_chat",
        req.project_id, tenant_id, req.connector_id, req.data_source_id
    )

    meeting_messages = [m for m in messages if m.get("message_type") == "meeting_event"]
    chat_messages = [m for m in messages if m.get("message_type") != "meeting_event"]

    meeting_threads = [{
        "id": str(_uuid.uuid4()),
        "messages": [m],
        "participants": {m.get("sender", "Unknown")},
        "started_at": _parse_dt(m.get("created_at", "")),
        "last_message_at": _parse_dt(m.get("created_at", "")),
        "has_audio": False, "has_video": False, "is_meeting": True,
    } for m in meeting_messages]

    openai_client = _make_openai_client()
    thread_engine = ThreadEngine(time_window_minutes=60, lookback_count=10, openai_client=openai_client)
    chat_threads = thread_engine.group_messages(chat_messages)

    processor = MessageProcessor(openai_client=openai_client, audio_processor=_audio_processor, teams_client=client)
    processed_meeting = [r for r in (processor.process_thread(t) for t in meeting_threads) if r is not None]
    processed_chat = [r for r in (processor.process_thread(t) for t in chat_threads) if r is not None]

    meeting_added = vector_ops.add_threads(
        processed_meeting, "microsoft_teams", "meeting", source_identifier,
        req.project_id, tenant_id, req.connector_id, req.data_source_id
    )
    chat_added = vector_ops.add_threads(
        processed_chat, "microsoft_teams", "group_chat", source_identifier,
        req.project_id, tenant_id, req.connector_id, req.data_source_id
    )
    added = meeting_added + chat_added

    all_threads = meeting_threads + chat_threads
    for thread in all_threads:
        msg_ids = [m["id"] for m in thread.get("messages", []) if m.get("id")]
        if msg_ids:
            vector_ops.update_thread_message_thread_ids(
                thread["id"], msg_ids, req.connector_id, req.data_source_id
            )

    extractor = WorkItemExtractor(openai_client=openai_client)
    for pt in processed_chat + processed_meeting:
        work_items = extractor.analyze_thread(pt)
        if work_items:
            vector_ops.store_work_items(
                work_items, pt["id"],
                tenant_id, req.project_id, req.connector_id, req.data_source_id,
                openai_client=openai_client
            )

    _record_sync_history(tenant_id, req.project_id, req.connector_id, req.data_source_id,
                         added, len(messages), "microsoft_teams", "group_chat")

    if req.data_source_id:
        _update_data_source_last_sync(req.data_source_id)

    processed_threads = processed_meeting + processed_chat
    audio_count = sum(1 for t in processed_threads if t.get("has_audio"))
    video_count = sum(1 for t in processed_threads if t.get("has_video"))

    return {
        "added": added,
        "total_fetched": len(messages),
        "threads": len(processed_threads),
        "meeting_threads": len(processed_meeting),
        "chat_threads": len(processed_chat),
        "audio_transcribed": audio_count,
        "video_transcribed": video_count,
    }


@app.post("/api/devops/list-projects")
def list_devops_projects(req: ListDevOpsProjectsRequest, user=Depends(verify_token)):
    try:
        client = _get_devops_client(req.connector_id, user["tenantId"])
        projects = client.get_projects()
        return {"projects": projects}
    except DevOpsApiError as e:
        logger.error(f"[DevOps] list-projects error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except requests.exceptions.HTTPError as e:
        body = e.response.text if e.response is not None else ""
        logger.error(f"[DevOps] list-projects HTTP error: {e} body={body}")
        raise HTTPException(status_code=400, detail=f"{e} — Response: {body[:500]}")
    except Exception as e:
        logger.error(f"[DevOps] list-projects unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/devops/list-iterations")
def list_devops_iterations(req: ListDevOpsIterationsRequest, user=Depends(verify_token)):
    try:
        client = _get_devops_client(req.connector_id, user["tenantId"])
        iterations = client.get_iterations(req.devops_project)
        return {"iterations": iterations}
    except DevOpsApiError as e:
        logger.error(f"[DevOps] list-iterations error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except requests.exceptions.HTTPError as e:
        body = e.response.text if e.response is not None else ""
        logger.error(f"[DevOps] list-iterations HTTP error: {e} body={body}")
        raise HTTPException(status_code=400, detail=f"{e} — Response: {body[:500]}")
    except Exception as e:
        logger.error(f"[DevOps] list-iterations unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sync/devops-project")
def sync_devops_project(req: SyncDevOpsProjectRequest, user=Depends(verify_token)):
    try:
        tenant_id = user["tenantId"]
        client = _get_devops_client(req.connector_id, tenant_id)

        source_identifier = {
            "organization": client.organization,
            "project_name": req.devops_project_name,
            "project_id": req.devops_project_id or "",
        }

        last_sync = vector_ops.get_last_sync(req.data_source_id)
        since = None
        if last_sync != "Never":
            try:
                since = datetime.fromisoformat(last_sync)
            except (ValueError, TypeError):
                since = None

        messages = fetch_devops_work_items_as_messages(client, req.devops_project_name, since)

        added = vector_ops.add_messages(
            messages, "azure_devops", "devops_project", source_identifier,
            req.project_id, tenant_id, req.connector_id, req.data_source_id
        )

        _record_sync_history(tenant_id, req.project_id, req.connector_id, req.data_source_id,
                             added, len(messages), "azure_devops", "devops_project")

        if req.data_source_id:
            _update_data_source_last_sync(req.data_source_id)

        work_items_count = sum(1 for m in messages if m.get("message_type") == "work_item")
        comments_count = sum(1 for m in messages if m.get("message_type") == "work_item_comment")

        return {
            "added": added,
            "total_fetched": len(messages),
            "work_items": work_items_count,
            "comments": comments_count,
        }
    except DevOpsApiError as e:
        logger.error(f"[DevOps] sync-devops-project error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except requests.exceptions.HTTPError as e:
        body = e.response.text if e.response is not None else ""
        logger.error(f"[DevOps] sync-devops-project HTTP error: {e} body={body}")
        raise HTTPException(status_code=400, detail=f"{e} — Response: {body[:500]}")
    except Exception as e:
        logger.error(f"[DevOps] sync-devops-project unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/devops/stats/{project_id}")
def get_devops_stats(project_id: str, user=Depends(verify_token)):
    tenant_id = user["tenantId"]
    stats = {
        "total_work_items": 0,
        "by_type": {},
        "by_state": {},
        "total_comments": 0,
    }
    try:
        with vector_ops._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT content, message_type FROM semantic_data
                       WHERE project_id = %s AND tenant_id = %s AND source_type = 'azure_devops'""",
                    (project_id, tenant_id),
                )
                rows = cur.fetchall()
                for content, msg_type in rows:
                    if msg_type == "work_item":
                        stats["total_work_items"] += 1
                        type_match = re_module.search(r'\[Type: ([^\]]+)\]', content or "")
                        state_match = re_module.search(r'\[State: ([^\]]+)\]', content or "")
                        if type_match:
                            t = type_match.group(1)
                            stats["by_type"][t] = stats["by_type"].get(t, 0) + 1
                        if state_match:
                            s = state_match.group(1)
                            stats["by_state"][s] = stats["by_state"].get(s, 0) + 1
                    elif msg_type == "work_item_comment":
                        stats["total_comments"] += 1
    except Exception as e:
        logger.error(f"DevOps stats query failed: {e}")
    return stats


@app.post("/api/search")
def search(req: SearchRequest, user=Depends(verify_token)):
    filters = {}
    if req.filter_team:
        filters["team"] = req.filter_team
    if req.filter_channel:
        filters["channel"] = req.filter_channel
    if req.filter_sender:
        filters["sender"] = req.filter_sender

    results = vector_ops.search(
        req.query, req.n_results, filters if filters else None, req.project_id, user["tenantId"]
    )
    return {"results": results}


@app.post("/api/ask")
def ask(req: AskRequest, user=Depends(verify_token)):
    filters = {}
    if req.filter_team:
        filters["team"] = req.filter_team
    if req.filter_channel:
        filters["channel"] = req.filter_channel

    results = vector_ops.search(
        req.question, 20, filters if filters else None, req.project_id, user["tenantId"]
    )

    answer = ask_question_ai(req.question, results, req.chat_history)
    return {"answer": answer, "sources": results[:10]}


@app.post("/api/summarize")
def summarize(req: SummarizeRequest, user=Depends(verify_token)):
    results = vector_ops.search(
        "project status updates decisions", 30, None, req.project_id, user["tenantId"]
    )
    if not results:
        return {"summary": "No messages found to summarize."}
    summary = summarize_ai(results)
    return {"summary": summary}


@app.get("/api/stats/{project_id}")
def get_stats(project_id: str, user=Depends(verify_token)):
    return vector_ops.get_stats(project_id, user["tenantId"])


class FindWorkItemRequest(BaseModel):
    query: str
    project_id: str


@app.post("/api/find-work-item")
def find_work_item(req: FindWorkItemRequest, user=Depends(verify_token)):
    tenant_id = user["tenantId"]
    openai_client = _make_openai_client()
    searcher = WorkItemSearch(openai_client=openai_client, vector_ops=vector_ops)
    result = searcher.find(req.query, req.project_id, tenant_id)
    return result


@app.delete("/api/project-data/{project_id}")
def clear_project_data(project_id: str, user=Depends(verify_token)):
    vector_ops.clear_project(project_id, user["tenantId"])
    return {"success": True}


def _record_sync_history(tenant_id: str, project_id: str, connector_id: str,
                         data_source_id: str, added: int, fetched: int,
                         source_type: str = None, segment_type: str = None):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO sync_history
                   (tenant_id, project_id, connector_id, data_source_id, source_type, segment_type,
                    status, records_added, records_fetched, completed_at)
                   VALUES (%s, %s, %s, %s, %s, %s, 'completed', %s, %s, NOW())""",
                (tenant_id, project_id, connector_id, data_source_id, source_type, segment_type, added, fetched),
            )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to record sync history: {e}")


def _update_data_source_last_sync(data_source_id: str):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE data_source SET last_sync_at = NOW() WHERE id = %s",
                (data_source_id,),
            )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to update data source last_sync_at: {e}")
