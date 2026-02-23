import os
import json
import logging
from datetime import datetime, timezone
import psycopg2
from apscheduler.schedulers.background import BackgroundScheduler

from teams_client import TeamsClient
from vector_ops import VectorOps
from encryption import decrypt_config

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")


class SyncScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.vector_ops = VectorOps()

    def start(self):
        self.scheduler.add_job(
            self._check_and_sync,
            "interval",
            minutes=1,
            id="sync_checker",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info("Sync scheduler started - checking every 1 minute")

    def stop(self):
        self.scheduler.shutdown(wait=False)

    def _check_and_sync(self):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT ds.id, ds.project_id, ds.tenant_id, ds.config, ds.encrypted_config,
                           ds.sync_interval_minutes, ds.last_sync_at, ds.source_type
                    FROM data_source ds
                    WHERE ds.sync_enabled = true
                      AND ds.sync_interval_minutes > 0
                      AND (
                        ds.last_sync_at IS NULL
                        OR ds.last_sync_at + (ds.sync_interval_minutes || ' minutes')::interval <= NOW()
                      )
                """)
                due_sources = cur.fetchall()
            conn.close()

            for source in due_sources:
                ds_id, project_id, tenant_id, config, encrypted_config, interval, last_sync, source_type = source

                actual_config = None
                if encrypted_config:
                    if isinstance(encrypted_config, str):
                        encrypted_config = json.loads(encrypted_config)
                    actual_config = decrypt_config(encrypted_config)
                elif config:
                    actual_config = config if isinstance(config, dict) else json.loads(config)
                else:
                    actual_config = {}

                logger.info(f"Auto-syncing data source {ds_id} (project={project_id}, type={source_type})")
                try:
                    if source_type == 'microsoft_teams':
                        self._sync_teams_source(ds_id, project_id, tenant_id, actual_config)
                    self._update_last_sync(ds_id)
                except Exception as e:
                    logger.error(f"Auto-sync failed for {ds_id}: {e}")
                    self._record_failed_sync(tenant_id, project_id, ds_id, str(e), source_type)

        except Exception as e:
            logger.error(f"Sync checker error: {e}")

    def _sync_teams_source(self, ds_id: str, project_id: str, tenant_id: str, config: dict):
        client_id = config.get("client_id", "")
        client_secret = config.get("client_secret", "")
        azure_tenant_id = config.get("tenant_id", "")

        if not all([client_id, client_secret, azure_tenant_id]):
            logger.warning(f"Data source {ds_id} missing credentials, skipping")
            return

        client = TeamsClient(client_id, client_secret, azure_tenant_id)
        teams = client.get_teams()

        total_added = 0
        total_fetched = 0

        for team in teams:
            try:
                channels = client.get_channels(team["id"])
                for channel in channels:
                    source_identifier = {
                        "team_id": team["id"],
                        "team_name": team["name"],
                        "channel_id": channel["id"],
                        "channel_name": channel["name"],
                    }

                    last_sync = self.vector_ops.get_last_sync(
                        "microsoft_teams", "team_channel", source_identifier, project_id, tenant_id
                    )
                    since = None
                    if last_sync != "Never":
                        try:
                            since = datetime.fromisoformat(last_sync)
                        except (ValueError, TypeError):
                            since = None

                    messages = client.get_channel_messages(team["id"], channel["id"], since=since)
                    added = self.vector_ops.add_messages(
                        messages, "microsoft_teams", "team_channel", source_identifier,
                        project_id, tenant_id, ds_id
                    )
                    self.vector_ops.update_sync_time(
                        "microsoft_teams", "team_channel", source_identifier,
                        project_id, tenant_id, ds_id
                    )

                    total_added += added
                    total_fetched += len(messages)
            except Exception as e:
                logger.error(f"Failed to sync team {team['name']}: {e}")

        self._record_sync(tenant_id, project_id, ds_id, total_added, total_fetched, "microsoft_teams")
        logger.info(f"Auto-sync complete for {ds_id}: {total_added} added, {total_fetched} fetched")

    def _update_last_sync(self, ds_id: str):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE data_source SET last_sync_at = NOW() WHERE id = %s",
                    (ds_id,),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to update last_sync_at: {e}")

    def _record_sync(self, tenant_id, project_id, ds_id, added, fetched, source_type=None):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO sync_history
                       (tenant_id, project_id, data_source_id, source_type, status,
                        records_added, records_fetched, completed_at)
                       VALUES (%s, %s, %s, %s, 'completed', %s, %s, NOW())""",
                    (tenant_id, project_id, ds_id, source_type, added, fetched),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to record sync: {e}")

    def _record_failed_sync(self, tenant_id, project_id, ds_id, error_msg, source_type=None):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO sync_history
                       (tenant_id, project_id, data_source_id, source_type, status,
                        error_message, completed_at)
                       VALUES (%s, %s, %s, %s, 'failed', %s, NOW())""",
                    (tenant_id, project_id, ds_id, source_type, error_msg[:500]),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to record failed sync: {e}")
