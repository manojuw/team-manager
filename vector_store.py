import os
import json
import hashlib
import logging
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384

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


class VectorStore:
    def __init__(self):
        self.database_url = os.environ.get("DATABASE_URL")
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable not set")
        self._init_tables()

    def _get_conn(self):
        return psycopg2.connect(self.database_url)

    def _init_tables(self):
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS teams_messages (
                        id TEXT PRIMARY KEY,
                        content TEXT NOT NULL,
                        embedding vector({EMBEDDING_DIM}),
                        sender TEXT,
                        created_at TEXT,
                        team TEXT,
                        channel TEXT,
                        message_type TEXT DEFAULT 'message',
                        message_id TEXT,
                        parent_message_id TEXT,
                        indexed_at TIMESTAMPTZ DEFAULT NOW(),
                        project_id TEXT
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS sync_metadata (
                        id TEXT PRIMARY KEY,
                        team_id TEXT NOT NULL,
                        channel_id TEXT NOT NULL,
                        last_sync TEXT NOT NULL,
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        project_id TEXT
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS projects (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT DEFAULT '',
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS project_data_sources (
                        id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                        source_type TEXT NOT NULL,
                        config JSONB DEFAULT '{}',
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_teams_messages_team
                    ON teams_messages(team);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_teams_messages_channel
                    ON teams_messages(channel);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_teams_messages_sender
                    ON teams_messages(sender);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_teams_messages_project
                    ON teams_messages(project_id);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_sync_metadata_project
                    ON sync_metadata(project_id);
                """)
                cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_teams_messages_embedding
                    ON teams_messages
                    USING hnsw (embedding vector_cosine_ops)
                    WITH (m = 16, ef_construction = 64);
                """)
            conn.commit()

    def create_project(self, name: str, description: str = "") -> dict:
        project_id = hashlib.md5(f"{name}-{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO projects (id, name, description) VALUES (%s, %s, %s)",
                        (project_id, name, description),
                    )
                conn.commit()
            return {"id": project_id, "name": name, "description": description}
        except Exception as e:
            logger.error(f"Create project failed: {e}")
            raise

    def get_projects(self) -> list:
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id, name, description, created_at FROM projects ORDER BY created_at DESC")
                    return [
                        {"id": row[0], "name": row[1], "description": row[2], "created_at": str(row[3])}
                        for row in cur.fetchall()
                    ]
        except Exception as e:
            logger.error(f"Get projects failed: {e}")
            return []

    def delete_project(self, project_id: str):
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM teams_messages WHERE project_id = %s", (project_id,))
                    cur.execute("DELETE FROM sync_metadata WHERE project_id = %s", (project_id,))
                    cur.execute("DELETE FROM projects WHERE id = %s", (project_id,))
                conn.commit()
        except Exception as e:
            logger.error(f"Delete project failed: {e}")
            raise

    def add_data_source(self, project_id: str, source_type: str, config: dict = None) -> dict:
        source_id = hashlib.md5(f"{project_id}-{source_type}-{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()
        config_json = json.dumps(config or {})
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO project_data_sources (id, project_id, source_type, config) VALUES (%s, %s, %s, %s)",
                        (source_id, project_id, source_type, config_json),
                    )
                conn.commit()
            return {"id": source_id, "project_id": project_id, "source_type": source_type, "config": config or {}}
        except Exception as e:
            logger.error(f"Add data source failed: {e}")
            raise

    def get_data_sources(self, project_id: str) -> list:
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, source_type, config, created_at FROM project_data_sources WHERE project_id = %s ORDER BY created_at",
                        (project_id,),
                    )
                    return [
                        {"id": row[0], "source_type": row[1], "config": row[2] if isinstance(row[2], dict) else json.loads(row[2] or "{}"), "created_at": str(row[3])}
                        for row in cur.fetchall()
                    ]
        except Exception as e:
            logger.error(f"Get data sources failed: {e}")
            return []

    def remove_data_source(self, source_id: str, project_id: str):
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM project_data_sources WHERE id = %s AND project_id = %s", (source_id, project_id))
                conn.commit()
        except Exception as e:
            logger.error(f"Remove data source failed: {e}")
            raise

    def _make_id(self, message: dict, project_id: str = None) -> str:
        raw = f"{project_id or ''}-{message.get('id', '')}-{message.get('created_at', '')}-{message.get('sender', '')}"
        return hashlib.md5(raw.encode()).hexdigest()

    def add_messages(self, messages: list, team_name: str, channel_name: str, project_id: str = None) -> int:
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
                        doc_id = self._make_id(msg, project_id)
                        cur.execute(
                            "SELECT 1 FROM teams_messages WHERE id = %s", (doc_id,)
                        )
                        if cur.fetchone():
                            continue

                        doc_text = (
                            f"[{msg.get('created_at', 'Unknown time')}] "
                            f"{msg['sender']}: {msg['content']}"
                        )
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
                    for (doc_id, msg, doc_text), embedding in zip(
                        new_msgs, embeddings
                    ):
                        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                        cur.execute(
                            """
                            INSERT INTO teams_messages 
                                (id, content, embedding, sender, created_at, team, channel, 
                                 message_type, message_id, parent_message_id, project_id)
                            VALUES (%s, %s, %s::vector, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO NOTHING
                            """,
                            (
                                doc_id,
                                doc_text,
                                embedding_str,
                                msg.get("sender", "Unknown"),
                                msg.get("created_at", ""),
                                team_name,
                                channel_name,
                                msg.get("message_type", "message"),
                                msg.get("id", ""),
                                msg.get("parent_message_id"),
                                project_id,
                            ),
                        )
                        added += 1
                conn.commit()

        logger.info(f"Added {added} new messages to PostgreSQL vector store (project={project_id})")
        return added

    def search(self, query: str, n_results: int = 20, filters: dict = None, project_id: str = None) -> list:
        try:
            query_embedding = get_embedding(query)
        except Exception as e:
            logger.error(f"Query embedding failed: {e}")
            return []

        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        where_clauses = []
        filter_params = []

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

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

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
                    rows = cur.fetchall()
                    for row in rows:
                        results.append(
                            {
                                "content": row[0],
                                "metadata": {
                                    "sender": row[1],
                                    "created_at": row[2],
                                    "team": row[3],
                                    "channel": row[4],
                                    "message_type": row[5],
                                    "message_id": row[6],
                                    "parent_message_id": row[7],
                                },
                                "relevance": float(row[8]) if row[8] else 0,
                            }
                        )
        except Exception as e:
            logger.error(f"Search failed: {e}")

        return results

    def get_stats(self, project_id: str = None) -> dict:
        stats = {"total_messages": 0, "teams": [], "channels": []}
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    if project_id:
                        cur.execute("SELECT COUNT(*) FROM teams_messages WHERE project_id = %s", (project_id,))
                    else:
                        cur.execute("SELECT COUNT(*) FROM teams_messages")
                    stats["total_messages"] = cur.fetchone()[0]

                    if project_id:
                        cur.execute(
                            "SELECT DISTINCT team FROM teams_messages WHERE team IS NOT NULL AND project_id = %s",
                            (project_id,),
                        )
                    else:
                        cur.execute(
                            "SELECT DISTINCT team FROM teams_messages WHERE team IS NOT NULL"
                        )
                    stats["teams"] = [row[0] for row in cur.fetchall()]

                    if project_id:
                        cur.execute(
                            "SELECT DISTINCT channel FROM teams_messages WHERE channel IS NOT NULL AND project_id = %s",
                            (project_id,),
                        )
                    else:
                        cur.execute(
                            "SELECT DISTINCT channel FROM teams_messages WHERE channel IS NOT NULL"
                        )
                    stats["channels"] = [row[0] for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Stats query failed: {e}")

        return stats

    def update_sync_time(self, team_id: str, channel_id: str, project_id: str = None):
        sync_id = f"sync-{project_id or 'global'}-{team_id}-{channel_id}"
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO sync_metadata (id, team_id, channel_id, last_sync, updated_at, project_id)
                        VALUES (%s, %s, %s, %s, NOW(), %s)
                        ON CONFLICT (id) DO UPDATE SET last_sync = %s, updated_at = NOW()
                        """,
                        (sync_id, team_id, channel_id, now, project_id, now),
                    )
                conn.commit()
        except Exception as e:
            logger.error(f"Sync time update failed: {e}")

    def get_last_sync(self, team_id: str, channel_id: str, project_id: str = None) -> str:
        sync_id = f"sync-{project_id or 'global'}-{team_id}-{channel_id}"
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT last_sync FROM sync_metadata WHERE id = %s",
                        (sync_id,),
                    )
                    row = cur.fetchone()
                    if row:
                        return row[0]
        except Exception as e:
            logger.error(f"Last sync query failed: {e}")
        return "Never"

    def clear_project(self, project_id: str):
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM teams_messages WHERE project_id = %s", (project_id,))
                    cur.execute("DELETE FROM sync_metadata WHERE project_id = %s", (project_id,))
                conn.commit()
            logger.info(f"Cleared all data for project {project_id}")
        except Exception as e:
            logger.error(f"Clear project failed: {e}")

    def clear_all(self):
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM teams_messages")
                    cur.execute("DELETE FROM sync_metadata")
                conn.commit()
            logger.info("Cleared all data from vector store")
        except Exception as e:
            logger.error(f"Clear failed: {e}")
