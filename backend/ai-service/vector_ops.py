import os
import hashlib
import logging
import json
import psycopg2
from datetime import datetime, timezone
from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384
DATABASE_URL = os.environ.get("DATABASE_URL")

_embedding_model = None


def _get_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = TextEmbedding()
    return _embedding_model


def get_embedding(text: str) -> list:
    model = _get_model()
    embeddings = list(model.embed([text]))
    return embeddings[0].tolist()


def get_embeddings_batch(texts: list) -> list:
    model = _get_model()
    embeddings = list(model.embed(texts))
    return [e.tolist() for e in embeddings]


class VectorOps:
    def _get_conn(self):
        return psycopg2.connect(DATABASE_URL)

    def _make_id(self, message: dict, project_id: str, tenant_id: str) -> str:
        raw = f"{tenant_id}-{project_id}-{message.get('id', '')}-{message.get('created_at', '')}-{message.get('sender', '')}"
        return hashlib.md5(raw.encode()).hexdigest()

    def add_messages(self, messages: list, source_type: str, segment_type: str,
                     source_identifier: dict, project_id: str, tenant_id: str,
                     data_source_id: str = None) -> int:
        if not messages:
            return 0
        added = 0
        batch_size = 50

        for i in range(0, len(messages), batch_size):
            batch = messages[i : i + batch_size]
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
                logger.error(f"Embedding generation failed: {e}")
                continue

            source_id_json = json.dumps(source_identifier)

            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    for (doc_id, msg, doc_text), embedding in zip(new_msgs, embeddings):
                        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                        cur.execute(
                            """INSERT INTO semantic_data
                               (id, tenant_id, project_id, data_source_id, source_type, segment_type,
                                source_identifier, content, embedding, sender, created_at,
                                message_type, message_id, parent_message_id)
                               VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::vector, %s, %s, %s, %s, %s)
                               ON CONFLICT (id) DO NOTHING""",
                            (
                                doc_id, tenant_id, project_id, data_source_id,
                                source_type, segment_type, source_id_json,
                                doc_text, embedding_str,
                                msg.get("sender", "Unknown"), msg.get("created_at", ""),
                                msg.get("message_type", "message"), msg.get("id", ""),
                                msg.get("parent_message_id"),
                            ),
                        )
                        added += 1
                conn.commit()

        logger.info(f"Added {added} new records (project={project_id}, tenant={tenant_id})")
        return added

    def search(self, query: str, n_results: int = 20, filters: dict = None, project_id: str = None, tenant_id: str = None) -> list:
        try:
            query_embedding = get_embedding(query)
        except Exception as e:
            logger.error(f"Query embedding failed: {e}")
            return []

        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
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
            if filters.get("team"):
                where_clauses.append("source_identifier->>'team_name' = %s")
                filter_params.append(filters["team"])
            if filters.get("channel"):
                where_clauses.append("source_identifier->>'channel_name' = %s")
                filter_params.append(filters["channel"])
            if filters.get("sender"):
                where_clauses.append("sender = %s")
                filter_params.append(filters["sender"])

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
                            },
                            "relevance": float(row[9]) if row[9] else 0,
                        })
        except Exception as e:
            logger.error(f"Search failed: {e}")
        return results

    def get_stats(self, project_id: str, tenant_id: str) -> dict:
        stats = {"total_records": 0, "source_types": [], "segment_types": [], "teams": [], "channels": []}
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM semantic_data WHERE project_id = %s AND tenant_id = %s", (project_id, tenant_id))
                    stats["total_records"] = cur.fetchone()[0]
                    cur.execute("SELECT DISTINCT source_type FROM semantic_data WHERE project_id = %s AND tenant_id = %s", (project_id, tenant_id))
                    stats["source_types"] = [row[0] for row in cur.fetchall()]
                    cur.execute("SELECT DISTINCT segment_type FROM semantic_data WHERE project_id = %s AND tenant_id = %s", (project_id, tenant_id))
                    stats["segment_types"] = [row[0] for row in cur.fetchall()]
                    cur.execute("SELECT DISTINCT source_identifier->>'team_name' FROM semantic_data WHERE source_identifier->>'team_name' IS NOT NULL AND project_id = %s AND tenant_id = %s", (project_id, tenant_id))
                    stats["teams"] = [row[0] for row in cur.fetchall() if row[0]]
                    cur.execute("SELECT DISTINCT source_identifier->>'channel_name' FROM semantic_data WHERE source_identifier->>'channel_name' IS NOT NULL AND project_id = %s AND tenant_id = %s", (project_id, tenant_id))
                    stats["channels"] = [row[0] for row in cur.fetchall() if row[0]]
        except Exception as e:
            logger.error(f"Stats query failed: {e}")
        return stats

    def update_sync_time(self, source_type: str, segment_type: str,
                         source_identifier: dict, project_id: str, tenant_id: str,
                         data_source_id: str = None):
        source_id_json = json.dumps(source_identifier, sort_keys=True)
        sync_id = f"sync-{tenant_id}-{project_id}-{hashlib.md5(source_id_json.encode()).hexdigest()}"
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO sync_metadata
                           (id, tenant_id, project_id, data_source_id, source_type, segment_type,
                            source_identifier, last_sync_at, updated_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, NOW())
                           ON CONFLICT (id) DO UPDATE SET last_sync_at = %s, updated_at = NOW()""",
                        (sync_id, tenant_id, project_id, data_source_id,
                         source_type, segment_type, source_id_json, now, now),
                    )
                conn.commit()
        except Exception as e:
            logger.error(f"Sync time update failed: {e}")

    def get_last_sync(self, source_type: str, segment_type: str,
                      source_identifier: dict, project_id: str, tenant_id: str) -> str:
        source_id_json = json.dumps(source_identifier, sort_keys=True)
        sync_id = f"sync-{tenant_id}-{project_id}-{hashlib.md5(source_id_json.encode()).hexdigest()}"
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT last_sync_at FROM sync_metadata WHERE id = %s", (sync_id,))
                    row = cur.fetchone()
                    if row and row[0]:
                        return row[0].isoformat() if hasattr(row[0], 'isoformat') else str(row[0])
        except Exception as e:
            logger.error(f"Last sync query failed: {e}")
        return "Never"

    def clear_project(self, project_id: str, tenant_id: str):
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM semantic_data WHERE project_id = %s AND tenant_id = %s", (project_id, tenant_id))
                    cur.execute("DELETE FROM sync_metadata WHERE project_id = %s AND tenant_id = %s", (project_id, tenant_id))
                conn.commit()
        except Exception as e:
            logger.error(f"Clear project failed: {e}")
