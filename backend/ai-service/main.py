import os
import logging
import hashlib
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import jwt

from teams_client import TeamsClient
from vector_ops import VectorOps
from ai_ops import ask_question_ai, summarize_ai
from scheduler import SyncScheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
JWT_SECRET = os.environ.get("SESSION_SECRET", "fallback-secret-key")

scheduler = SyncScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    data_source_id: str
    team_id: str
    team_name: str
    channel_id: str
    channel_name: str


class SyncGroupChatRequest(BaseModel):
    project_id: str
    data_source_id: str
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
    data_source_id: str


class ListChannelsRequest(BaseModel):
    data_source_id: str
    team_id: str


class ListUsersRequest(BaseModel):
    data_source_id: str


class ListGroupChatsRequest(BaseModel):
    data_source_id: str
    user_ids: list[str]


def _get_teams_client(data_source_id: str, tenant_id: str) -> TeamsClient:
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT config FROM project_data_sources WHERE id = %s AND tenant_id = %s",
                (data_source_id, tenant_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Data source not found")
            config = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            client_id = config.get("client_id", "")
            client_secret = config.get("client_secret", "")
            azure_tenant_id = config.get("tenant_id", "")
            if not all([client_id, client_secret, azure_tenant_id]):
                raise HTTPException(status_code=400, detail="Data source credentials not configured")
            return TeamsClient(client_id, client_secret, azure_tenant_id)
    finally:
        conn.close()


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "ai-service"}


@app.post("/api/teams/list-teams")
def list_teams(req: ListTeamsRequest, user=Depends(verify_token)):
    client = _get_teams_client(req.data_source_id, user["tenantId"])
    teams = client.get_teams()
    return {"teams": teams}


@app.post("/api/teams/list-channels")
def list_channels(req: ListChannelsRequest, user=Depends(verify_token)):
    client = _get_teams_client(req.data_source_id, user["tenantId"])
    channels = client.get_channels(req.team_id)
    return {"channels": channels}


@app.post("/api/teams/list-users")
def list_users(req: ListUsersRequest, user=Depends(verify_token)):
    client = _get_teams_client(req.data_source_id, user["tenantId"])
    users = client.get_users()
    return {"users": users}


@app.post("/api/teams/list-group-chats")
def list_group_chats(req: ListGroupChatsRequest, user=Depends(verify_token)):
    client = _get_teams_client(req.data_source_id, user["tenantId"])
    chats = client.get_group_chats(user_ids=req.user_ids)
    return {"chats": chats}


@app.post("/api/sync/channel")
def sync_channel(req: SyncChannelRequest, user=Depends(verify_token)):
    tenant_id = user["tenantId"]
    client = _get_teams_client(req.data_source_id, tenant_id)

    last_sync = vector_ops.get_last_sync(req.team_id, req.channel_id, req.project_id, tenant_id)
    since = None
    if last_sync != "Never":
        try:
            since = datetime.fromisoformat(last_sync)
        except (ValueError, TypeError):
            since = None

    messages = client.get_channel_messages(req.team_id, req.channel_id, since=since)
    added = vector_ops.add_messages(messages, req.team_name, req.channel_name, req.project_id, tenant_id)
    vector_ops.update_sync_time(req.team_id, req.channel_id, req.project_id, tenant_id)

    _record_sync_history(tenant_id, req.project_id, req.data_source_id, added, len(messages))

    replies_count = sum(1 for m in messages if m.get("message_type") == "reply")
    posts_count = len(messages) - replies_count

    return {
        "added": added,
        "total_fetched": len(messages),
        "posts": posts_count,
        "replies": replies_count,
    }


@app.post("/api/sync/group-chat")
def sync_group_chat(req: SyncGroupChatRequest, user=Depends(verify_token)):
    tenant_id = user["tenantId"]
    client = _get_teams_client(req.data_source_id, tenant_id)

    sync_key = f"chat-{req.chat_id}"
    last_sync = vector_ops.get_last_sync(sync_key, "group_chat", req.project_id, tenant_id)
    since = None
    if last_sync != "Never":
        try:
            since = datetime.fromisoformat(last_sync)
        except (ValueError, TypeError):
            since = None

    messages = client.get_chat_messages(req.chat_id, since=since)
    added = vector_ops.add_messages(messages, req.chat_name, "Group Chat", req.project_id, tenant_id)
    vector_ops.update_sync_time(sync_key, "group_chat", req.project_id, tenant_id)

    _record_sync_history(tenant_id, req.project_id, req.data_source_id, added, len(messages))

    return {"added": added, "total_fetched": len(messages)}


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


@app.delete("/api/project-data/{project_id}")
def clear_project_data(project_id: str, user=Depends(verify_token)):
    vector_ops.clear_project(project_id, user["tenantId"])
    return {"success": True}


def _record_sync_history(tenant_id: str, project_id: str, data_source_id: str, added: int, fetched: int):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO sync_history (tenant_id, project_id, data_source_id, status, messages_added, messages_fetched, completed_at)
                   VALUES (%s, %s, %s, 'completed', %s, %s, NOW())""",
                (tenant_id, project_id, data_source_id, added, fetched),
            )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to record sync history: {e}")
