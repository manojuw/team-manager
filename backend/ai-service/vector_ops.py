import os
import hashlib
import logging
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

    def add_messages(self, messages: list, team_name: str, channel_name: str, project_id: str, tenant_id: str) -> int:
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
                        cur.execute("SELECT 1 FROM teams_messages WHERE id = %s", (doc_id,))
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

            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    for (doc_id, msg, doc_text), embedding in zip(new_msgs, embeddings):
                        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                        cur.execute(
                            """INSERT INTO teams_messages
                               (id, tenant_id, project_id, content, embedding, sender, created_at, team, channel,
                                message_type, message_id, parent_message_id)
                               VALUES (%s, %s, %s, %s, %s::vector, %s, %s, %s, %s, %s, %s, %s)
                               ON CONFLICT (id) DO NOTHING""",
                            (
                                doc_id, tenant_id, project_id, doc_text, embedding_str,
                                msg.get("sender", "Unknown"), msg.get("created_at", ""),
                                team_name, channel_name,
                                msg.get("message_type", "message"), msg.get("id", ""),
                                msg.get("parent_message_id"),
                            ),
                        )
                        added += 1
                conn.commit()

        logger.info(f"Added {added} new messages (project={project_id}, tenant={tenant_id})")
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
            if filters.get("team"):
                where_clauses.append("team = %s")
                filter_params.append(filters["team"])
            if filters.get("channel"):
                where_clauses.append("channel = %s")
                filter_params.append(filters["channel"])
            if filters.get("sender"):
                where_clauses.append("sender = %s")
                filter_params.append(filters["sender"])

        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        sql = f"""
            SELECT content, sender, created_at, team, channel, message_type,
                   message_id, parent_message_id,
                   1 - (embedding <=> %s::vector) AS relevance
            FROM teams_messages
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
                        results.append({
                            "content": row[0],
                            "metadata": {
                                "sender": row[1], "created_at": row[2],
                                "team": row[3], "channel": row[4],
                                "message_type": row[5], "message_id": row[6],
                                "parent_message_id": row[7],
                            },
                            "relevance": float(row[8]) if row[8] else 0,
                        })
        except Exception as e:
            logger.error(f"Search failed: {e}")
        return results

    def get_stats(self, project_id: str, tenant_id: str) -> dict:
        stats = {"total_messages": 0, "teams": [], "channels": []}
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM teams_messages WHERE project_id = %s AND tenant_id = %s", (project_id, tenant_id))
                    stats["total_messages"] = cur.fetchone()[0]
                    cur.execute("SELECT DISTINCT team FROM teams_messages WHERE team IS NOT NULL AND project_id = %s AND tenant_id = %s", (project_id, tenant_id))
                    stats["teams"] = [row[0] for row in cur.fetchall()]
                    cur.execute("SELECT DISTINCT channel FROM teams_messages WHERE channel IS NOT NULL AND project_id = %s AND tenant_id = %s", (project_id, tenant_id))
                    stats["channels"] = [row[0] for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Stats query failed: {e}")
        return stats

    def update_sync_time(self, team_id: str, channel_id: str, project_id: str, tenant_id: str):
        sync_id = f"sync-{tenant_id}-{project_id}-{team_id}-{channel_id}"
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO sync_metadata (id, tenant_id, project_id, team_id, channel_id, last_sync, updated_at)
                           VALUES (%s, %s, %s, %s, %s, %s, NOW())
                           ON CONFLICT (id) DO UPDATE SET last_sync = %s, updated_at = NOW()""",
                        (sync_id, tenant_id, project_id, team_id, channel_id, now, now),
                    )
                conn.commit()
        except Exception as e:
            logger.error(f"Sync time update failed: {e}")

    def get_last_sync(self, team_id: str, channel_id: str, project_id: str, tenant_id: str) -> str:
        sync_id = f"sync-{tenant_id}-{project_id}-{team_id}-{channel_id}"
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT last_sync FROM sync_metadata WHERE id = %s", (sync_id,))
                    row = cur.fetchone()
                    if row:
                        return row[0]
        except Exception as e:
            logger.error(f"Last sync query failed: {e}")
        return "Never"

    def clear_project(self, project_id: str, tenant_id: str):
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM teams_messages WHERE project_id = %s AND tenant_id = %s", (project_id, tenant_id))
                    cur.execute("DELETE FROM sync_metadata WHERE project_id = %s AND tenant_id = %s", (project_id, tenant_id))
                conn.commit()
        except Exception as e:
            logger.error(f"Clear project failed: {e}")
