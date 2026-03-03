import os
import re
import json
import logging
from datetime import datetime, timezone
import psycopg2
from apscheduler.schedulers.background import BackgroundScheduler

import uuid as _uuid
from teams_client import TeamsClient
from vector_ops import VectorOps
from encryption import decrypt_config
from azure_devops_client import AzureDevOpsClient
from thread_engine import ThreadEngine, _parse_dt
from message_processor import MessageProcessor
from audio_processor import AudioProcessor
from openai import OpenAI as _OpenAI

_audio_processor = AudioProcessor()


def _make_openai_client():
    api_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return _OpenAI(**kwargs)

logger = logging.getLogger(__name__)

UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE
)
DOMAIN_PATTERN = re.compile(
    r'^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)

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
                    SELECT ds.id, ds.connector_id, ds.project_id, ds.tenant_id,
                           ds.source_type, ds.config, ds.sync_interval_minutes, ds.last_sync_at,
                           c.config AS connector_config, c.encrypted_config, c.connector_type
                    FROM data_source ds
                    JOIN connector c ON c.id = ds.connector_id
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
                (ds_id, connector_id, project_id, tenant_id, source_type, ds_config,
                 interval, last_sync, connector_config, encrypted_config, connector_type) = source

                actual_config = None
                if encrypted_config:
                    if isinstance(encrypted_config, str):
                        encrypted_config = json.loads(encrypted_config)
                    actual_config = decrypt_config(encrypted_config)
                elif connector_config:
                    actual_config = connector_config if isinstance(connector_config, dict) else json.loads(connector_config)
                else:
                    actual_config = {}

                ds_cfg = ds_config if isinstance(ds_config, dict) else (json.loads(ds_config) if ds_config else {})

                if connector_type == 'microsoft_teams' and not self._validate_teams_config(actual_config, ds_id):
                    continue
                if connector_type == 'azure_devops' and not self._validate_devops_config(actual_config, ds_id):
                    continue

                logger.info(f"Auto-syncing data source {ds_id} (connector={connector_id}, type={connector_type}/{source_type})")
                try:
                    if connector_type == 'microsoft_teams':
                        self._sync_teams_data_source(ds_id, connector_id, project_id, tenant_id,
                                                     source_type, ds_cfg, actual_config)
                    elif connector_type == 'azure_devops':
                        self._sync_devops_data_source(ds_id, connector_id, project_id, tenant_id,
                                                       source_type, ds_cfg, actual_config)
                    self._update_last_sync(ds_id)
                except Exception as e:
                    logger.error(f"Auto-sync failed for {ds_id}: {e}")
                    self._record_failed_sync(tenant_id, project_id, connector_id, ds_id, str(e),
                                             connector_type, source_type)

        except Exception as e:
            logger.error(f"Sync checker error: {e}")

    def _validate_teams_config(self, config: dict, ds_id: str) -> bool:
        client_id = config.get("client_id", "")
        client_secret = config.get("client_secret", "")
        azure_tenant_id = config.get("tenant_id", "")

        if not all([client_id, client_secret, azure_tenant_id]):
            logger.warning(f"Connector for data source {ds_id} missing credentials, skipping")
            return False

        if client_secret == "••••••••" or len(client_secret) < 8:
            logger.warning(f"Connector for data source {ds_id} has masked/invalid client_secret, skipping")
            return False

        if not (UUID_PATTERN.match(azure_tenant_id) or DOMAIN_PATTERN.match(azure_tenant_id)):
            logger.warning(f"Connector for data source {ds_id} has invalid tenant_id '{azure_tenant_id}', skipping (must be a GUID or domain)")
            return False

        if not UUID_PATTERN.match(client_id):
            logger.warning(f"Connector for data source {ds_id} has invalid client_id '{client_id}', skipping (must be a GUID)")
            return False

        return True

    def _sync_teams_data_source(self, ds_id: str, connector_id: str, project_id: str,
                                 tenant_id: str, source_type: str, ds_config: dict,
                                 connector_config: dict):
        client_id = connector_config.get("client_id", "")
        client_secret = connector_config.get("client_secret", "")
        azure_tenant_id = connector_config.get("tenant_id", "")

        client = TeamsClient(client_id, client_secret, azure_tenant_id)

        if source_type == "team_channel":
            team_id = ds_config.get("team_id", "")
            channel_id = ds_config.get("channel_id", "")
            team_name = ds_config.get("team_name", "")
            channel_name = ds_config.get("channel_name", "")
            if not team_id or not channel_id:
                logger.warning(f"Data source {ds_id} missing team/channel config, skipping")
                return

            source_identifier = {
                "team_id": team_id, "team_name": team_name,
                "channel_id": channel_id, "channel_name": channel_name,
            }
            last_sync = self.vector_ops.get_last_sync(ds_id)
            since = None
            if last_sync != "Never":
                try:
                    since = datetime.fromisoformat(last_sync)
                except (ValueError, TypeError):
                    since = None

            messages = client.get_channel_messages(team_id, channel_id, since=since)

            self.vector_ops.insert_raw_messages(
                messages, "microsoft_teams", "team_channel",
                project_id, tenant_id, connector_id, ds_id
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

            meeting_added = self.vector_ops.add_threads(
                processed_meeting, "microsoft_teams", "meeting", source_identifier,
                project_id, tenant_id, connector_id, ds_id
            )
            chat_added = self.vector_ops.add_threads(
                processed_chat, "microsoft_teams", "team_channel", source_identifier,
                project_id, tenant_id, connector_id, ds_id
            )

            all_threads = meeting_threads + chat_threads
            for thread in all_threads:
                msg_ids = [m["id"] for m in thread.get("messages", []) if m.get("id")]
                if msg_ids:
                    self.vector_ops.update_thread_message_thread_ids(
                        thread["id"], msg_ids, connector_id, ds_id
                    )

            self._record_sync(tenant_id, project_id, connector_id, ds_id,
                              meeting_added + chat_added, len(messages), "microsoft_teams", "team_channel")

        elif source_type == "group_chat":
            chat_id = ds_config.get("chat_id", "")
            chat_name = ds_config.get("chat_name", "")
            if not chat_id:
                logger.warning(f"Data source {ds_id} missing chat config, skipping")
                return

            source_identifier = {"chat_id": chat_id, "chat_name": chat_name}
            last_sync = self.vector_ops.get_last_sync(ds_id)
            since = None
            if last_sync != "Never":
                try:
                    since = datetime.fromisoformat(last_sync)
                except (ValueError, TypeError):
                    since = None

            messages = client.get_chat_messages(chat_id, since=since)

            self.vector_ops.insert_raw_messages(
                messages, "microsoft_teams", "group_chat",
                project_id, tenant_id, connector_id, ds_id
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

            meeting_added = self.vector_ops.add_threads(
                processed_meeting, "microsoft_teams", "meeting", source_identifier,
                project_id, tenant_id, connector_id, ds_id
            )
            chat_added = self.vector_ops.add_threads(
                processed_chat, "microsoft_teams", "group_chat", source_identifier,
                project_id, tenant_id, connector_id, ds_id
            )

            all_threads = meeting_threads + chat_threads
            for thread in all_threads:
                msg_ids = [m["id"] for m in thread.get("messages", []) if m.get("id")]
                if msg_ids:
                    self.vector_ops.update_thread_message_thread_ids(
                        thread["id"], msg_ids, connector_id, ds_id
                    )

            self._record_sync(tenant_id, project_id, connector_id, ds_id,
                              meeting_added + chat_added, len(messages), "microsoft_teams", "group_chat")

        logger.info(f"Auto-sync complete for data source {ds_id}")

    def _validate_devops_config(self, config: dict, ds_id: str) -> bool:
        organization = config.get("organization", "")
        if not organization:
            logger.warning(f"DevOps connector for data source {ds_id} missing organization, skipping")
            return False

        auth_type = config.get("auth_type", "pat")
        if auth_type == "pat":
            pat = config.get("pat", "")
            if not pat or pat == "••••••••" or len(pat) < 8:
                logger.warning(f"DevOps connector for data source {ds_id} has invalid PAT, skipping")
                return False
        else:
            client_id = config.get("client_id", "")
            client_secret = config.get("client_secret", "")
            azure_tenant_id = config.get("tenant_id", "")
            if not all([client_id, client_secret, azure_tenant_id]):
                logger.warning(f"DevOps connector for data source {ds_id} missing Azure AD credentials, skipping")
                return False
            if client_secret == "••••••••" or len(client_secret) < 8:
                logger.warning(f"DevOps connector for data source {ds_id} has masked/invalid client_secret, skipping")
                return False

        return True

    def _sync_devops_data_source(self, ds_id: str, connector_id: str, project_id: str,
                                  tenant_id: str, source_type: str, ds_config: dict,
                                  connector_config: dict):
        organization = connector_config.get("organization", "")
        auth_type = connector_config.get("auth_type", "pat")

        if auth_type == "pat":
            client = AzureDevOpsClient(organization=organization, auth_type="pat",
                                        pat=connector_config.get("pat", ""))
        else:
            client = AzureDevOpsClient(
                organization=organization, auth_type="azure_ad",
                client_id=connector_config.get("client_id", ""),
                client_secret=connector_config.get("client_secret", ""),
                tenant_id=connector_config.get("tenant_id", ""),
            )

        if source_type == "devops_project":
            devops_project = ds_config.get("devops_project_name", ds_config.get("devops_project", ""))
            if not devops_project:
                logger.warning(f"Data source {ds_id} missing devops_project_name config, skipping")
                return

            source_identifier = {
                "organization": organization,
                "project_name": devops_project,
                "project_id": ds_config.get("devops_project_id", ""),
            }

            last_sync = self.vector_ops.get_last_sync(ds_id)
            since = None
            if last_sync != "Never":
                try:
                    since = datetime.fromisoformat(last_sync)
                except (ValueError, TypeError):
                    since = None

            from devops_sync import fetch_devops_work_items_as_messages
            messages = fetch_devops_work_items_as_messages(client, devops_project, since)

            added = self.vector_ops.add_messages(
                messages, "azure_devops", "devops_project", source_identifier,
                project_id, tenant_id, connector_id, ds_id
            )
            self._record_sync(tenant_id, project_id, connector_id, ds_id,
                              added, len(messages), "azure_devops", "devops_project")

        logger.info(f"Auto-sync complete for DevOps data source {ds_id}")

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

    def _record_sync(self, tenant_id, project_id, connector_id, ds_id, added, fetched,
                     source_type=None, segment_type=None):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO sync_history
                       (tenant_id, project_id, connector_id, data_source_id, source_type, segment_type,
                        status, records_added, records_fetched, completed_at)
                       VALUES (%s, %s, %s, %s, %s, %s, 'completed', %s, %s, NOW())""",
                    (tenant_id, project_id, connector_id, ds_id, source_type, segment_type, added, fetched),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to record sync: {e}")

    def _record_failed_sync(self, tenant_id, project_id, connector_id, ds_id, error_msg,
                            source_type=None, segment_type=None):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO sync_history
                       (tenant_id, project_id, connector_id, data_source_id, source_type, segment_type,
                        status, error_message, completed_at)
                       VALUES (%s, %s, %s, %s, %s, %s, 'failed', %s, NOW())""",
                    (tenant_id, project_id, connector_id, ds_id, source_type, segment_type, error_msg[:500]),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to record failed sync: {e}")
