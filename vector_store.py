import os
import hashlib
import logging
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
from openai import OpenAI

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

AI_INTEGRATIONS_OPENAI_API_KEY = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
AI_INTEGRATIONS_OPENAI_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")

openai_client = OpenAI(
    api_key=AI_INTEGRATIONS_OPENAI_API_KEY,
    base_url=AI_INTEGRATIONS_OPENAI_BASE_URL,
)


def get_embedding(text: str) -> list:
    text = text[:8000]
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


def get_embeddings_batch(texts: list) -> list:
    texts = [t[:8000] for t in texts]
    batch_size = 100
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
        )
        all_embeddings.extend([d.embedding for d in response.data])
    return all_embeddings


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
                        indexed_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS sync_metadata (
                        id TEXT PRIMARY KEY,
                        team_id TEXT NOT NULL,
                        channel_id TEXT NOT NULL,
                        last_sync TEXT NOT NULL,
                        updated_at TIMESTAMPTZ DEFAULT NOW()
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
                cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_teams_messages_embedding
                    ON teams_messages
                    USING hnsw (embedding vector_cosine_ops)
                    WITH (m = 16, ef_construction = 64);
                """)
            conn.commit()

    def _make_id(self, message: dict) -> str:
        raw = f"{message.get('id', '')}-{message.get('created_at', '')}-{message.get('sender', '')}"
        return hashlib.md5(raw.encode()).hexdigest()

    def add_messages(self, messages: list, team_name: str, channel_name: str) -> int:
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
                        doc_id = self._make_id(msg)
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
                                 message_type, message_id, parent_message_id)
                            VALUES (%s, %s, %s::vector, %s, %s, %s, %s, %s, %s, %s)
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
                            ),
                        )
                        added += 1
                conn.commit()

        logger.info(f"Added {added} new messages to PostgreSQL vector store")
        return added

    def search(self, query: str, n_results: int = 20, filters: dict = None) -> list:
        try:
            query_embedding = get_embedding(query)
        except Exception as e:
            logger.error(f"Query embedding failed: {e}")
            return []

        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        where_clauses = []
        filter_params = []

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

    def get_stats(self) -> dict:
        stats = {"total_messages": 0, "teams": [], "channels": []}
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM teams_messages")
                    stats["total_messages"] = cur.fetchone()[0]

                    cur.execute(
                        "SELECT DISTINCT team FROM teams_messages WHERE team IS NOT NULL"
                    )
                    stats["teams"] = [row[0] for row in cur.fetchall()]

                    cur.execute(
                        "SELECT DISTINCT channel FROM teams_messages WHERE channel IS NOT NULL"
                    )
                    stats["channels"] = [row[0] for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Stats query failed: {e}")

        return stats

    def update_sync_time(self, team_id: str, channel_id: str):
        sync_id = f"sync-{team_id}-{channel_id}"
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO sync_metadata (id, team_id, channel_id, last_sync, updated_at)
                        VALUES (%s, %s, %s, %s, NOW())
                        ON CONFLICT (id) DO UPDATE SET last_sync = %s, updated_at = NOW()
                        """,
                        (sync_id, team_id, channel_id, now, now),
                    )
                conn.commit()
        except Exception as e:
            logger.error(f"Sync time update failed: {e}")

    def get_last_sync(self, team_id: str, channel_id: str) -> str:
        sync_id = f"sync-{team_id}-{channel_id}"
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
