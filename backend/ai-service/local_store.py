import sqlite3
import os
import json
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_DB_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(_DB_DIR, "local_state.db")


def _get_conn():
    os.makedirs(_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _get_conn()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_job (
            id TEXT PRIMARY KEY,
            tenant_id TEXT,
            data_source_id TEXT,
            connector_id TEXT,
            project_id TEXT,
            source_type TEXT,
            status TEXT DEFAULT 'running',
            started_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT,
            result TEXT,
            error TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audio_chunk_cache (
            cache_key TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            transcript TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (cache_key, chunk_index)
        )
    """)
    conn.commit()
    conn.close()
    cleanup_on_startup()
    logger.info("[LocalStore] SQLite initialized at %s", DB_PATH)


def cleanup_on_startup():
    conn = _get_conn()
    cur = conn.execute("DELETE FROM sync_job WHERE status='running'")
    deleted_jobs = cur.rowcount
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    cur2 = conn.execute("DELETE FROM audio_chunk_cache WHERE created_at < ?", (cutoff,))
    deleted_chunks = cur2.rowcount
    conn.commit()
    conn.close()
    if deleted_jobs:
        logger.info(f"[LocalStore] Cleaned up {deleted_jobs} stale running job(s) on startup")
    if deleted_chunks:
        logger.info(f"[LocalStore] Cleaned up {deleted_chunks} old audio cache entries (>24h)")


def create_job(job_id, tenant_id, data_source_id, connector_id, project_id, source_type):
    conn = _get_conn()
    conn.execute(
        """INSERT INTO sync_job (id, tenant_id, data_source_id, connector_id, project_id, source_type)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (job_id, tenant_id, data_source_id or "", connector_id or "", project_id or "", source_type or "")
    )
    conn.commit()
    conn.close()


def complete_job(job_id, result: dict):
    conn = _get_conn()
    conn.execute(
        "UPDATE sync_job SET status='completed', completed_at=datetime('now'), result=? WHERE id=?",
        (json.dumps(result), job_id)
    )
    conn.commit()
    conn.close()


def fail_job(job_id, error: str):
    conn = _get_conn()
    conn.execute(
        "UPDATE sync_job SET status='failed', completed_at=datetime('now'), error=? WHERE id=?",
        (str(error)[:2000], job_id)
    )
    conn.commit()
    conn.close()


def get_job(job_id, tenant_id):
    conn = _get_conn()
    cur = conn.execute(
        "SELECT status, result, error, started_at, completed_at FROM sync_job WHERE id=? AND tenant_id=?",
        (job_id, tenant_id)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    result_raw = row["result"]
    result_parsed = None
    if result_raw:
        try:
            result_parsed = json.loads(result_raw)
        except Exception:
            result_parsed = result_raw
    return {
        "status": row["status"],
        "result": result_parsed,
        "error": row["error"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


def cache_get_chunk(cache_key: str, chunk_index: int):
    try:
        conn = _get_conn()
        cur = conn.execute(
            "SELECT transcript FROM audio_chunk_cache WHERE cache_key=? AND chunk_index=?",
            (cache_key, chunk_index)
        )
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def cache_set_chunk(cache_key: str, chunk_index: int, transcript: str):
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO audio_chunk_cache (cache_key, chunk_index, transcript) VALUES (?, ?, ?)",
            (cache_key, chunk_index, transcript)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
