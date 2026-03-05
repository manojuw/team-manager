import os
import re
import uuid
import hashlib
import logging
import json
import psycopg2
from datetime import datetime, timezone
from openai import OpenAI

logger = logging.getLogger(__name__)


def _expand_queries_for_devops_match(openai_client, title: str, description: str) -> list:
    base = [
        title,
        f"{title}. {description[:150]}" if description else title,
    ]
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Generate 3 alternative search queries to find work items related to the given title and description. "
                        "Use different phrasings, synonyms, and angles. Respond with JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Title: {title}\nDescription: {description[:200]}\n\n"
                        "Return JSON only: {\"queries\": [\"...\", \"...\", \"...\"]}"
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=150,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        extras = [q for q in data.get("queries", []) if q and q not in base]
        base.extend(extras[:3])
    except Exception as e:
        logger.warning(f"[VectorOps] Query expansion failed: {e}")
    result = list(dict.fromkeys(base))[:5]
    logger.info(f"[VectorOps] DevOps match queries: {result}")
    return result


def _confirm_devops_match_with_gpt(openai_client, suggested_title: str, suggested_desc: str, devops_content: str) -> bool:
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You determine if two work item descriptions refer to the same issue or task. "
                        "Be strict but account for different phrasings. Respond with JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Suggested work item:\nTitle: {suggested_title}\nDescription: {suggested_desc[:300]}\n\n"
                        f"Existing DevOps item:\n{devops_content[:500]}\n\n"
                        "Are these about the same issue or task? "
                        "Return JSON only: {\"same_issue\": true or false, \"reason\": \"brief\"}"
                    ),
                },
            ],
            temperature=0,
            max_tokens=80,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        same = bool(data.get("same_issue", False))
        reason = data.get("reason", "")
        logger.info(f"[VectorOps] GPT says same_issue={same} reason='{reason}'")
        return same
    except Exception as e:
        logger.warning(f"[VectorOps] GPT confirmation failed: {e}")
        return False


EMBEDDING_DIM = 1536
EMBEDDING_MODEL = "text-embedding-3-small"
DATABASE_URL = os.environ.get("DATABASE_URL")

_embeddings_client = None


def _get_embeddings_client():
    global _embeddings_client
    if _embeddings_client is None:
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
        _embeddings_client = OpenAI(api_key=api_key)
    return _embeddings_client


def get_embedding(text: str) -> list:
    client = _get_embeddings_client()
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=text[:8000])
    return response.data[0].embedding


def get_embeddings_batch(texts: list) -> list:
    if not texts:
        return []
    client = _get_embeddings_client()
    truncated = [t[:8000] for t in texts]
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=truncated)
    return [item.embedding for item in response.data]


class VectorOps:
    def _get_conn(self):
        return psycopg2.connect(DATABASE_URL)

    def _make_id(self, message: dict, project_id: str, tenant_id: str) -> str:
        raw = f"{tenant_id}-{project_id}-{message.get('id', '')}-{message.get('created_at', '')}-{message.get('sender', '')}"
        return hashlib.md5(raw.encode()).hexdigest()

    def add_threads(self, threads: list, source_type: str, segment_type: str,
                    source_identifier: dict, project_id: str, tenant_id: str,
                    connector_id: str = None, data_source_id: str = None) -> int:
        if not threads:
            return 0
        added = 0
        source_id_json = json.dumps(source_identifier)

        for thread in threads:
            clarified = thread.get("clarified_content", "")
            embedding = thread.get("embedding", [])
            if not clarified or not embedding:
                logger.warning("[VectorOps] Skipping thread with missing content or embedding")
                continue

            raw_messages = thread.get("messages", [])
            participants = list(thread.get("participants") or [])
            started_at = thread.get("started_at")
            last_message_at = thread.get("last_message_at")
            started_by = raw_messages[0].get("sender", "") if raw_messages else ""
            message_count = len(raw_messages)
            has_audio = thread.get("has_audio", False)
            has_video = thread.get("has_video", False)
            summary = thread.get("summary", "") or ""
            task_planning = thread.get("task_planning", "") or ""

            def _dt(v):
                if v is None:
                    return None
                if isinstance(v, datetime):
                    return v.isoformat()
                return str(v)

            serializable_messages = []
            for m in raw_messages:
                sm = {k: v for k, v in m.items() if isinstance(v, (str, int, float, bool, list, dict, type(None)))}
                serializable_messages.append(sm)

            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

            thread_id = thread.get("id") or str(uuid.uuid4())

            try:
                with self._get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """INSERT INTO thread
                               (id, tenant_id, project_id, connector_id, data_source_id,
                                source_type, segment_type, source_identifier,
                                raw_messages, clarified_content, embedding,
                                started_by, participants, message_count,
                                has_audio, has_video, started_at, last_message_at,
                                summary, task_planning)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                                       %s::jsonb, %s, %s::vector,
                                       %s, %s::jsonb, %s,
                                       %s, %s, %s, %s,
                                       %s, %s)
                               ON CONFLICT (id) DO NOTHING""",
                            (
                                thread_id,
                                tenant_id, project_id, connector_id, data_source_id,
                                source_type, segment_type, source_id_json,
                                json.dumps(serializable_messages), clarified, embedding_str,
                                started_by, json.dumps(participants), message_count,
                                has_audio, has_video, _dt(started_at), _dt(last_message_at),
                                summary, task_planning,
                            ),
                        )
                        if cur.rowcount > 0:
                            added += 1
                        else:
                            logger.warning(f"[VectorOps] Thread {thread_id} already exists (ON CONFLICT DO NOTHING)")
                    conn.commit()
            except Exception as e:
                logger.error(f"[VectorOps] Failed to insert thread {thread_id}: {e}", exc_info=True)

        logger.info(f"[VectorOps] Added {added} threads (project={project_id})")
        return added

    def insert_raw_messages(self, messages: list, source_type: str, segment_type: str,
                            project_id: str, tenant_id: str,
                            connector_id: str = None, data_source_id: str = None) -> int:
        if not messages:
            return 0
        inserted = 0
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    for msg in messages:
                        msg_id = msg.get("id", "")
                        if not msg_id:
                            continue
                        raw_copy = {k: v for k, v in msg.items()
                                    if isinstance(v, (str, int, float, bool, list, dict, type(None)))}
                        cur.execute(
                            """INSERT INTO thread_message
                               (message_id, tenant_id, project_id, connector_id, data_source_id,
                                source_type, segment_type, sender, content, created_at, raw_message)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                               ON CONFLICT (message_id, connector_id, data_source_id) DO NOTHING""",
                            (
                                msg_id, tenant_id, project_id, connector_id, data_source_id,
                                source_type, segment_type,
                                msg.get("sender", ""),
                                (msg.get("content") or "")[:2000],
                                msg.get("created_at"),
                                json.dumps(raw_copy),
                            ),
                        )
                        if cur.rowcount:
                            inserted += 1
                conn.commit()
        except Exception as e:
            logger.error(f"[VectorOps] Failed to insert raw messages: {e}")
        logger.info(f"[VectorOps] Inserted {inserted} raw messages into thread_message")
        return inserted

    def update_thread_message_thread_ids(self, thread_id: str, message_ids: list,
                                          connector_id: str = None, data_source_id: str = None) -> None:
        if not message_ids or not thread_id:
            return
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """UPDATE thread_message SET thread_id = %s
                           WHERE message_id = ANY(%s)
                           AND connector_id IS NOT DISTINCT FROM %s
                           AND data_source_id IS NOT DISTINCT FROM %s""",
                        (thread_id, message_ids, connector_id, data_source_id),
                    )
                conn.commit()
        except Exception as e:
            logger.error(f"[VectorOps] Failed to update thread_message thread_ids: {e}")

    def add_messages(self, messages: list, source_type: str, segment_type: str,
                     source_identifier: dict, project_id: str, tenant_id: str,
                     connector_id: str = None, data_source_id: str = None) -> int:
        if not messages:
            return 0
        added = 0
        batch_size = 50

        for i in range(0, len(messages), batch_size):
            batch = messages[i: i + batch_size]
            new_msgs = []

            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    for msg in batch:
                        doc_id = self._make_id(msg, project_id, tenant_id)
                        cur.execute("SELECT 1 FROM semantic_data WHERE id = %s", (doc_id,))
                        if cur.fetchone():
                            continue
                        doc_text = f"[{msg.get('created_at', 'Unknown time')}] {msg['sender']}: {msg['content']}"
                        new_msgs.append((doc_id, msg, doc_text))

            if not new_msgs:
                continue

            texts = [item[2] for item in new_msgs]
            try:
                embeddings = get_embeddings_batch(texts)
            except Exception as e:
                logger.error(f"[VectorOps] Embedding generation failed: {e}")
                continue

            source_id_json = json.dumps(source_identifier)

            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    for (doc_id, msg, doc_text), embedding in zip(new_msgs, embeddings):
                        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                        cur.execute(
                            """INSERT INTO semantic_data
                               (id, tenant_id, project_id, connector_id, data_source_id,
                                source_type, segment_type, source_identifier, content, embedding,
                                sender, created_at, message_type, message_id, parent_message_id)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::vector, %s, %s, %s, %s, %s)
                               ON CONFLICT (id) DO NOTHING""",
                            (
                                doc_id, tenant_id, project_id, connector_id, data_source_id,
                                source_type, segment_type, source_id_json,
                                doc_text, embedding_str,
                                msg.get("sender", "Unknown"), msg.get("created_at", ""),
                                msg.get("message_type", "message"), msg.get("id", ""),
                                msg.get("parent_message_id"),
                            ),
                        )
                        added += 1
                conn.commit()

        logger.info(f"[VectorOps] Added {added} records (project={project_id})")
        return added

    def search(self, query: str, n_results: int = 20, filters: dict = None,
               project_id: str = None, tenant_id: str = None) -> list:
        try:
            query_embedding = get_embedding(query)
        except Exception as e:
            logger.error(f"[VectorOps] Query embedding failed: {e}")
            return []

        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        results = []

        results += self._search_threads(embedding_str, n_results, filters, project_id, tenant_id)

        results += self._search_semantic(embedding_str, n_results, filters, project_id, tenant_id)

        results.sort(key=lambda r: r["relevance"], reverse=True)
        return results[:n_results]

    def _search_threads(self, embedding_str: str, n_results: int, filters: dict,
                        project_id: str, tenant_id: str) -> list:
        where_clauses = []
        filter_params = []

        if tenant_id:
            where_clauses.append("tenant_id = %s")
            filter_params.append(tenant_id)
        if project_id:
            where_clauses.append("project_id = %s")
            filter_params.append(project_id)
        if filters:
            if filters.get("source_type"):
                where_clauses.append("source_type = %s")
                filter_params.append(filters["source_type"])

        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        sql = f"""
            SELECT clarified_content, started_by, started_at, last_message_at,
                   source_type, segment_type, source_identifier,
                   participants, message_count, has_audio, has_video,
                   1 - (embedding <=> %s::vector) AS relevance
            FROM thread
            {where_sql}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        params = [embedding_str] + filter_params + [embedding_str, n_results]

        results = []
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    for row in cur.fetchall():
                        source_id = row[6] if isinstance(row[6], dict) else json.loads(row[6]) if row[6] else {}
                        participants = row[7] if isinstance(row[7], list) else json.loads(row[7]) if row[7] else []
                        results.append({
                            "content": row[0],
                            "metadata": {
                                "sender": row[1],
                                "created_at": str(row[2]) if row[2] else "",
                                "last_message_at": str(row[3]) if row[3] else "",
                                "source_type": row[4],
                                "segment_type": row[5],
                                "source_identifier": source_id,
                                "team": source_id.get("team_name", ""),
                                "channel": source_id.get("channel_name", ""),
                                "participants": participants,
                                "message_count": row[8],
                                "has_audio": row[9],
                                "has_video": row[10],
                                "result_type": "thread",
                            },
                            "relevance": float(row[11]) if row[11] else 0,
                        })
        except Exception as e:
            logger.error(f"[VectorOps] Thread search failed: {e}")
        return results

    def _search_semantic(self, embedding_str: str, n_results: int, filters: dict,
                         project_id: str, tenant_id: str) -> list:
        where_clauses = []
        filter_params = []

        if tenant_id:
            where_clauses.append("tenant_id = %s")
            filter_params.append(tenant_id)
        if project_id:
            where_clauses.append("project_id = %s")
            filter_params.append(project_id)
        if filters:
            if filters.get("source_type"):
                where_clauses.append("source_type = %s")
                filter_params.append(filters["source_type"])
            if filters.get("segment_type"):
                where_clauses.append("segment_type = %s")
                filter_params.append(filters["segment_type"])

        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        sql = f"""
            SELECT content, sender, created_at, source_type, segment_type,
                   source_identifier, message_type, message_id, parent_message_id,
                   1 - (embedding <=> %s::vector) AS relevance
            FROM semantic_data
            {where_sql}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        params = [embedding_str] + filter_params + [embedding_str, n_results]

        results = []
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    for row in cur.fetchall():
                        source_id = row[5] if isinstance(row[5], dict) else json.loads(row[5]) if row[5] else {}
                        results.append({
                            "content": row[0],
                            "metadata": {
                                "sender": row[1], "created_at": row[2],
                                "source_type": row[3], "segment_type": row[4],
                                "source_identifier": source_id,
                                "team": source_id.get("team_name", ""),
                                "channel": source_id.get("channel_name", ""),
                                "message_type": row[6], "message_id": row[7],
                                "parent_message_id": row[8],
                                "result_type": "message",
                            },
                            "relevance": float(row[9]) if row[9] else 0,
                        })
        except Exception as e:
            logger.error(f"[VectorOps] Semantic search failed: {e}")
        return results

    def get_stats(self, project_id: str, tenant_id: str) -> dict:
        stats = {"total_messages": 0, "unique_teams": 0, "unique_channels": 0, "unique_senders": 0}
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT
                             COUNT(*),
                             COUNT(DISTINCT source_identifier->>'team_name') FILTER (WHERE source_identifier->>'team_name' IS NOT NULL),
                             COUNT(DISTINCT source_identifier->>'channel_name') FILTER (WHERE source_identifier->>'channel_name' IS NOT NULL),
                             COUNT(DISTINCT started_by) FILTER (WHERE started_by IS NOT NULL)
                           FROM thread
                           WHERE project_id = %s AND tenant_id = %s""",
                        (project_id, tenant_id),
                    )
                    row = cur.fetchone()
                    if row:
                        stats["total_messages"] = row[0] or 0
                        stats["unique_teams"] = row[1] or 0
                        stats["unique_channels"] = row[2] or 0
                        stats["unique_senders"] = row[3] or 0
        except Exception as e:
            logger.error(f"[VectorOps] Stats query failed: {e}")
        return stats

    def get_last_sync(self, data_source_id: str) -> str:
        if not data_source_id:
            return "Never"
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT last_sync_at FROM data_source WHERE id = %s", (data_source_id,))
                    row = cur.fetchone()
                    if row and row[0]:
                        return row[0].isoformat() if hasattr(row[0], 'isoformat') else str(row[0])
        except Exception as e:
            logger.error(f"[VectorOps] Last sync query failed: {e}")
        return "Never"

    def search_devops_candidates(self, queries: list, tenant_id: str, project_id: str, n_results: int = 5) -> list:
        scored = {}
        total = len(queries)
        for i, q in enumerate(queries):
            try:
                emb = get_embedding(q)
                emb_str = "[" + ",".join(str(x) for x in emb) + "]"
                with self._get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """SELECT id, content, 1 - (embedding <=> %s::vector) AS sim
                               FROM semantic_data
                               WHERE tenant_id = %s AND project_id = %s
                                 AND source_type = 'azure_devops'
                                 AND embedding IS NOT NULL
                               ORDER BY embedding <=> %s::vector
                               LIMIT %s""",
                            (emb_str, tenant_id, project_id, emb_str, n_results),
                        )
                        rows = cur.fetchall()
                logger.info(
                    f"[VectorOps/DevOps] Query [{i+1}/{total}]: '{q[:60]}' → {len(rows)} results"
                )
                for row in rows:
                    item_id = str(row[0])
                    content = row[1] or ""
                    sim = float(row[2]) if row[2] else 0.0
                    logger.info(f"  title='{content[:60]}' sim={sim:.3f}")
                    if item_id not in scored or scored[item_id]["sim"] < sim:
                        scored[item_id] = {"id": item_id, "content": content, "sim": sim}
            except Exception as e:
                logger.warning(f"[VectorOps/DevOps] Query failed for '{q}': {e}")

        candidates = sorted(scored.values(), key=lambda x: x["sim"], reverse=True)
        logger.info(f"[VectorOps/DevOps] Candidate pool: {len(candidates)} unique DevOps items")
        for c in candidates:
            first_line = c.get("content", "").split("\n")[0]
            m_id = re.search(r'\[Work Item #(\d+)\]', first_line)
            c["devops_work_item_id"] = m_id.group(1) if m_id else None
            m_title = re.search(r'\[Work Item #\d+\] (.+)', first_line)
            c["devops_work_item_title"] = m_title.group(1).strip() if m_title else None
        return candidates[:n_results]

    def _insert_work_item_row(self, cur, tenant_id, project_id, connector_id, data_source_id,
                              thread_id, title, description, source_message_ids, embedding_str,
                              semantic_data_id, devops_work_item_id, devops_work_item_title,
                              item_type, assigned_to, parent_id) -> str:
        cur.execute(
            """INSERT INTO suggested_work_item
               (tenant_id, project_id, connector_id, data_source_id,
                thread_id, title, description, source_message_ids,
                embedding, semantic_data_id, devops_work_item_id, devops_work_item_title,
                item_type, assigned_to, parent_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (
                tenant_id, project_id, connector_id, data_source_id,
                thread_id, title, description,
                source_message_ids if source_message_ids else [],
                embedding_str,
                semantic_data_id,
                devops_work_item_id,
                devops_work_item_title,
                item_type,
                assigned_to,
                parent_id,
            ),
        )
        row = cur.fetchone()
        return str(row[0]) if row else None

    def _resolve_devops_match(self, title, description, embedding_str, tenant_id, project_id, openai_client):
        semantic_data_id = None
        devops_work_item_id = None
        devops_work_item_title = None
        try:
            if openai_client:
                queries = _expand_queries_for_devops_match(openai_client, title, description)
                candidates = self.search_devops_candidates(queries, tenant_id, project_id, n_results=5)
                logger.info(f"[VectorOps] DevOps candidate pool: {len(candidates)} unique items across {len(queries)} queries")
                for cand in candidates:
                    if cand["sim"] >= 0.35:
                        confirmed = _confirm_devops_match_with_gpt(
                            openai_client, title, description, cand["content"]
                        )
                        if confirmed:
                            semantic_data_id = cand["id"]
                            devops_work_item_id = cand.get("devops_work_item_id")
                            devops_work_item_title = cand.get("devops_work_item_title")
                            logger.info(
                                f"[VectorOps] → GPT confirmed DevOps match: {semantic_data_id} "
                                f"(work_item_id={devops_work_item_id}, sim={cand['sim']:.3f})"
                            )
                            break
                        else:
                            logger.info(f"[VectorOps] → GPT rejected candidate (sim={cand['sim']:.3f})")
                if not semantic_data_id:
                    logger.info("[VectorOps] → No confirmed DevOps match found")
            else:
                with self._get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """SELECT id, content, 1 - (embedding <=> %s::vector) AS similarity
                               FROM semantic_data
                               WHERE tenant_id = %s AND project_id = %s
                                 AND source_type = 'azure_devops'
                                 AND embedding IS NOT NULL
                               ORDER BY embedding <=> %s::vector
                               LIMIT 1""",
                            (embedding_str, tenant_id, project_id, embedding_str),
                        )
                        row = cur.fetchone()
                        if row:
                            sim = float(row[2]) if row[2] else 0.0
                            if sim >= 0.82:
                                semantic_data_id = str(row[0])
                                first_line = (row[1] or "").split("\n")[0]
                                m_id = re.search(r'\[Work Item #(\d+)\]', first_line)
                                devops_work_item_id = m_id.group(1) if m_id else None
                                m_title = re.search(r'\[Work Item #\d+\] (.+)', first_line)
                                devops_work_item_title = m_title.group(1).strip() if m_title else None
                                logger.info(f"[VectorOps] → Fallback match: {semantic_data_id} (sim={sim:.3f})")
                            else:
                                logger.info(f"[VectorOps] → No fallback match (best sim={sim:.3f})")
        except Exception as e:
            logger.warning(f"[VectorOps] DevOps match lookup failed: {e}")
        return semantic_data_id, devops_work_item_id, devops_work_item_title

    def store_work_items(self, work_items: list, thread_id: str,
                         tenant_id: str, project_id: str,
                         connector_id: str = None, data_source_id: str = None,
                         openai_client=None) -> int:
        if not work_items:
            return 0

        stored = 0
        parent_uuid = None

        for item in work_items:
            title = item.get("title", "")
            description = item.get("description", "")
            source_message_ids = item.get("source_message_ids", [])
            item_type = item.get("item_type", "Task")
            assigned_to = item.get("assigned_to")
            is_parent = item.get("is_parent", False)

            if not title:
                continue
            try:
                embed_text = f"{title}. {description}"[:2000]
                embedding = get_embedding(embed_text)
                embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

                semantic_data_id = None
                devops_work_item_id = None
                devops_work_item_title = None

                if item_type != "UserStory":
                    logger.info(f"[VectorOps] Checking DevOps match for: '{title}'")
                    semantic_data_id, devops_work_item_id, devops_work_item_title = (
                        self._resolve_devops_match(title, description, embedding_str, tenant_id, project_id, openai_client)
                    )

                parent_id = None if is_parent else parent_uuid

                with self._get_conn() as conn:
                    with conn.cursor() as cur:
                        new_id = self._insert_work_item_row(
                            cur,
                            tenant_id, project_id, connector_id, data_source_id,
                            thread_id, title, description, source_message_ids, embedding_str,
                            semantic_data_id, devops_work_item_id, devops_work_item_title,
                            item_type, assigned_to, parent_id,
                        )
                        if source_message_ids:
                            cur.execute(
                                """UPDATE thread_message SET is_work_item_related = TRUE
                                   WHERE message_id = ANY(%s)
                                   AND connector_id IS NOT DISTINCT FROM %s
                                   AND data_source_id IS NOT DISTINCT FROM %s""",
                                (source_message_ids, connector_id, data_source_id),
                            )
                    conn.commit()

                if is_parent and new_id:
                    parent_uuid = new_id
                    logger.info(f"[VectorOps] Stored UserStory parent with id={parent_uuid}")

                stored += 1
            except Exception as e:
                logger.error(f"[VectorOps] Failed to store work item '{title}': {e}")

        logger.info(f"[VectorOps] Stored {stored} suggested work item(s) for thread {thread_id}")
        return stored

    def search_work_items(self, query: str, project_id: str, tenant_id: str, n_results: int = 10) -> list:
        try:
            embedding = get_embedding(query)
        except Exception as e:
            logger.error(f"[VectorOps] Work item search embedding failed: {e}")
            return []
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
        results = []

        suggested_results = []
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT id, title, description, status, thread_id, created_at,
                                  1 - (embedding <=> %s::vector) AS relevance
                           FROM suggested_work_item
                           WHERE tenant_id = %s AND project_id = %s
                             AND embedding IS NOT NULL
                           ORDER BY embedding <=> %s::vector
                           LIMIT %s""",
                        (embedding_str, tenant_id, project_id, embedding_str, n_results),
                    )
                    for row in cur.fetchall():
                        suggested_results.append({
                            "id": str(row[0]),
                            "title": row[1],
                            "description": row[2],
                            "status": row[3],
                            "thread_id": str(row[4]) if row[4] else None,
                            "created_at": str(row[5]) if row[5] else None,
                            "source": "suggested",
                            "relevance": float(row[6]) if row[6] else 0.0,
                        })
            logger.info(
                f"[WorkItemSearch/DB] suggested_work_item: {len(suggested_results)} results "
                f"for query '{query[:50]}'"
            )
            for i, r in enumerate(suggested_results):
                logger.info(
                    f"  [{i}] title='{r['title'][:60]}' "
                    f"relevance={r['relevance']:.3f} source=suggested"
                )
            results.extend(suggested_results)
        except Exception as e:
            logger.error(f"[VectorOps] search_work_items (suggested) failed: {e}")

        devops_results = []
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT id, content, sender, created_at, message_id,
                                  1 - (embedding <=> %s::vector) AS relevance
                           FROM semantic_data
                           WHERE tenant_id = %s AND project_id = %s
                             AND source_type = 'azure_devops'
                           ORDER BY embedding <=> %s::vector
                           LIMIT %s""",
                        (embedding_str, tenant_id, project_id, embedding_str, n_results),
                    )
                    for row in cur.fetchall():
                        content = row[1] or ""
                        lines = content.splitlines()
                        title = lines[0][:80] if lines else content[:80]
                        devops_results.append({
                            "id": str(row[0]),
                            "title": title,
                            "description": content[:500],
                            "status": None,
                            "thread_id": None,
                            "created_at": str(row[3]) if row[3] else None,
                            "source": "azure_devops",
                            "relevance": float(row[5]) if row[5] else 0.0,
                        })
            logger.info(
                f"[WorkItemSearch/DB] semantic_data(devops): {len(devops_results)} results "
                f"for query '{query[:50]}'"
            )
            for i, r in enumerate(devops_results):
                logger.info(
                    f"  [{i}] title='{r['title'][:60]}' "
                    f"relevance={r['relevance']:.3f} source=azure_devops"
                )
            results.extend(devops_results)
        except Exception as e:
            logger.error(f"[VectorOps] search_work_items (semantic_data) failed: {e}")

        results.sort(key=lambda r: r["relevance"], reverse=True)
        top = results[:n_results]
        logger.info(
            f"[WorkItemSearch/DB] Merged: {len(results)} total results, returning top {len(top)}"
        )
        return top

    def clear_project(self, project_id: str, tenant_id: str):
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM thread WHERE project_id = %s AND tenant_id = %s", (project_id, tenant_id))
                    cur.execute("DELETE FROM semantic_data WHERE project_id = %s AND tenant_id = %s", (project_id, tenant_id))
                    cur.execute("UPDATE data_source SET last_sync_at = NULL WHERE project_id = %s AND tenant_id = %s", (project_id, tenant_id))
                conn.commit()
        except Exception as e:
            logger.error(f"[VectorOps] Clear project failed: {e}")
