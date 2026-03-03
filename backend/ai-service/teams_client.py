import base64
import logging
import re
import msal
import requests
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_API_BETA = "https://graph.microsoft.com/beta"

MEETING_EVENT_TYPES = {
    "#microsoft.graph.callRecordingEventMessageDetail",
    "#microsoft.graph.callTranscriptionEventMessageDetail",
}

def _extract_html_text(content: str) -> str:
    content = re.sub(r"<[^>]+>", " ", content)
    content = re.sub(r"\s+", " ", content).strip()
    return content


def _extract_sender(msg: dict) -> str:
    sender = msg.get("from", {})
    user_info = sender.get("user", {}) if sender else {}
    return user_info.get("displayName", "Unknown") if user_info else "System"


def _extract_attachments(msg: dict) -> list:
    attachments = msg.get("attachments", [])
    result = []
    for att in attachments:
        info = {
            "name": att.get("name", ""),
            "content_type": att.get("contentType", ""),
            "content_url": att.get("contentUrl", ""),
            "id": att.get("id", ""),
            "card_content": att.get("content", ""),
        }
        result.append(info)
    return result


class TeamsClient:
    def __init__(self, client_id: str, client_secret: str, tenant_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.access_token = None
        self.token_expiry = 0
        self._app = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
        )

    def _ensure_token(self):
        if self.access_token and time.time() < self.token_expiry - 60:
            return
        result = self._app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        if "access_token" in result:
            self.access_token = result["access_token"]
            self.token_expiry = time.time() + result.get("expires_in", 3600)
        else:
            error = result.get("error_description", result.get("error", "Unknown error"))
            raise Exception(f"Failed to acquire token: {error}")

    def _headers(self, advanced_query: bool = False):
        self._ensure_token()
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        if advanced_query:
            headers["ConsistencyLevel"] = "eventual"
        return headers

    def _get(self, url: str, params: dict = None, advanced_query: bool = False) -> dict:
        response = requests.get(
            url, headers=self._headers(advanced_query=advanced_query), params=params
        )
        response.raise_for_status()
        return response.json()

    def _get_raw(self, url: str) -> bytes:
        self._ensure_token()
        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.content

    def _get_all_pages(
        self, url: str, params: dict = None, max_pages: int = 50, advanced_query: bool = False
    ) -> list:
        all_items = []
        page = 0
        while url and page < max_pages:
            data = self._get(url, params=params if page == 0 else None, advanced_query=advanced_query)
            all_items.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
            page += 1
        return all_items

    def get_teams(self) -> list:
        url = (
            f"{GRAPH_API_BASE}/groups"
            f"?$filter=resourceProvisioningOptions/Any(x:x eq 'Team')"
            f"&$count=true"
            f"&$select=id,displayName,description"
        )
        teams = self._get_all_pages(url, advanced_query=True)
        return [{"id": t["id"], "displayName": t.get("displayName", "Unknown")} for t in teams]

    def get_channels(self, team_id: str) -> list:
        url = f"{GRAPH_API_BASE}/teams/{team_id}/channels"
        channels = self._get_all_pages(url)
        return [
            {
                "id": c["id"],
                "displayName": c.get("displayName", "Unknown"),
                "description": c.get("description", ""),
            }
            for c in channels
        ]

    def get_channel_messages(
        self, team_id: str, channel_id: str, since: datetime = None, top: int = 50
    ) -> list:
        url = f"{GRAPH_API_BASE}/teams/{team_id}/channels/{channel_id}/messages"
        params = {"$top": top}
        messages = self._get_all_pages(url, params=params, max_pages=20)

        logger.info(
            f"Fetched {len(messages)} top-level messages from API (since={since})"
        )

        results = []
        total_replies_fetched = 0
        for msg in messages:
            created = msg.get("createdDateTime", "")
            msg_id = msg.get("id", "")

            is_new_message = True
            if since and created:
                try:
                    msg_time = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if msg_time < since:
                        is_new_message = False
                except (ValueError, TypeError):
                    pass

            if is_new_message:
                event_detail = msg.get("eventDetail")
                if event_detail:
                    event_type = event_detail.get("@odata.type", "")
                    if event_type in MEETING_EVENT_TYPES:
                        results.append({
                            "id": msg_id,
                            "content": "",
                            "sender": _extract_sender(msg),
                            "created_at": created,
                            "attachments": [],
                            "message_type": "meeting_event",
                            "event_detail": event_detail,
                            "source_base_url": f"teams/{team_id}/channels/{channel_id}",
                        })

                body = msg.get("body", {})
                content = body.get("content", "")
                content_type = body.get("contentType", "text")

                if content_type == "html":
                    content = _extract_html_text(content)

                attachment_info = _extract_attachments(msg)

                if content.strip():
                    results.append({
                        "id": msg_id,
                        "content": content,
                        "sender": _extract_sender(msg),
                        "created_at": created,
                        "attachments": attachment_info,
                        "message_type": msg.get("messageType", "message"),
                        "source_base_url": f"teams/{team_id}/channels/{channel_id}",
                    })
                elif attachment_info:
                    results.append({
                        "id": msg_id,
                        "content": f"[Attachment: {', '.join(a['name'] for a in attachment_info if a['name'])}]",
                        "sender": _extract_sender(msg),
                        "created_at": created,
                        "attachments": attachment_info,
                        "message_type": msg.get("messageType", "message"),
                        "source_base_url": f"teams/{team_id}/channels/{channel_id}",
                    })

            replies = self._get_message_replies(team_id, channel_id, msg_id)
            total_replies_fetched += len(replies)
            for reply in replies:
                results.append(reply)

        logger.info(
            f"Sync results: {len(results)} total items "
            f"({len(messages)} top-level, {total_replies_fetched} replies fetched)"
        )

        return results

    def _get_message_replies(self, team_id: str, channel_id: str, message_id: str) -> list:
        if not message_id:
            return []
        url = f"{GRAPH_API_BASE}/teams/{team_id}/channels/{channel_id}/messages/{message_id}/replies"
        try:
            replies = self._get_all_pages(url, max_pages=5)
        except requests.exceptions.HTTPError:
            return []

        results = []
        for reply in replies:
            body = reply.get("body", {})
            content = body.get("content", "")
            content_type = body.get("contentType", "text")

            if content_type == "html":
                content = _extract_html_text(content)

            reply_attachment_info = _extract_attachments(reply)
            if content.strip() or reply_attachment_info:
                results.append({
                    "id": reply.get("id", ""),
                    "content": content,
                    "sender": _extract_sender(reply),
                    "created_at": reply.get("createdDateTime", ""),
                    "attachments": reply_attachment_info,
                    "message_type": "reply",
                    "parent_message_id": message_id,
                    "source_base_url": f"teams/{team_id}/channels/{channel_id}",
                })

        return results

    def get_users(self) -> list:
        url = f"{GRAPH_API_BASE}/users"
        params = {
            "$select": "id,displayName,mail,userPrincipalName",
            "$top": 100,
        }
        users = self._get_all_pages(url, params=params, max_pages=10)
        return [
            {
                "id": u["id"],
                "displayName": u.get("displayName", "Unknown"),
                "mail": u.get("mail") or u.get("userPrincipalName", ""),
            }
            for u in users
            if u.get("displayName")
        ]

    def get_group_chats(self, user_ids: list = None) -> list:
        all_chats = {}
        for user_id in (user_ids or []):
            url = f"{GRAPH_API_BASE}/users/{user_id}/chats"
            params = {
                "$filter": "chatType eq 'group'",
                "$select": "id,topic,chatType,createdDateTime,lastUpdatedDateTime",
                "$top": 50,
            }
            try:
                chats = self._get_all_pages(url, params=params, max_pages=5)
            except Exception as e:
                logger.warning(f"Failed to fetch chats for user {user_id}: {e}")
                continue

            for chat in chats:
                chat_id = chat.get("id", "")
                if chat_id and chat_id not in all_chats:
                    all_chats[chat_id] = chat

        results = []
        for chat_id, chat in all_chats.items():
            member_names = []
            try:
                members_url = f"{GRAPH_API_BASE}/chats/{chat_id}/members"
                fetched = self._get_all_pages(members_url, max_pages=1)
                member_names = [
                    m.get("displayName", "Unknown")
                    for m in fetched
                    if m.get("displayName")
                ]
            except Exception:
                pass

            topic = chat.get("topic", "")
            display_name = topic if topic else ", ".join(member_names[:5])
            if len(member_names) > 5:
                display_name += f" +{len(member_names) - 5} more"

            results.append({
                "id": chat_id,
                "topic": topic or display_name or "Unnamed Chat",
                "members": [{"displayName": n} for n in member_names],
                "last_updated": chat.get("lastUpdatedDateTime", ""),
            })
        return results

    def get_chat_messages(self, chat_id: str, since: datetime = None, top: int = 50) -> list:
        url = f"{GRAPH_API_BASE}/chats/{chat_id}/messages"
        params = {"$top": top}
        messages = self._get_all_pages(url, params=params, max_pages=10)

        results = []
        for msg in messages:
            created = msg.get("createdDateTime", "")
            msg_id = msg.get("id", "")

            if since and created:
                try:
                    msg_time = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if msg_time <= since:
                        continue
                except (ValueError, TypeError):
                    pass

            event_detail = msg.get("eventDetail")
            if event_detail:
                event_type = event_detail.get("@odata.type", "")
                if event_type in MEETING_EVENT_TYPES:
                    results.append({
                        "id": msg_id,
                        "content": "",
                        "sender": _extract_sender(msg),
                        "created_at": created,
                        "attachments": [],
                        "message_type": "meeting_event",
                        "event_detail": event_detail,
                        "source_base_url": f"chats/{chat_id}",
                    })

            body = msg.get("body", {})
            content = body.get("content", "")
            content_type = body.get("contentType", "text")

            if content_type == "html":
                content = _extract_html_text(content)

            attachment_info = _extract_attachments(msg)

            if content.strip():
                results.append({
                    "id": msg_id,
                    "content": content,
                    "sender": _extract_sender(msg),
                    "created_at": created,
                    "attachments": attachment_info,
                    "message_type": msg.get("messageType", "message"),
                    "source_base_url": f"chats/{chat_id}",
                })
            elif attachment_info:
                results.append({
                    "id": msg_id,
                    "content": f"[Attachment: {', '.join(a['name'] for a in attachment_info if a['name'])}]",
                    "sender": _extract_sender(msg),
                    "created_at": created,
                    "attachments": attachment_info,
                    "message_type": msg.get("messageType", "message"),
                    "source_base_url": f"chats/{chat_id}",
                })

        return results

    def _encode_sharing_url(self, url: str) -> str:
        encoded = base64.b64encode(url.encode("utf-8")).decode("utf-8")
        encoded = encoded.rstrip("=").replace("/", "_").replace("+", "-")
        return f"u!{encoded}"

    def download_via_sharing_url(self, sharepoint_url: str) -> bytes:
        sharing_token = self._encode_sharing_url(sharepoint_url)
        url = f"{GRAPH_API_BASE}/shares/{sharing_token}/driveItem/content"
        try:
            return self._get_raw(url)
        except Exception as e:
            logger.warning(f"Failed to download via sharing URL: {e}")
            return b""

    def download_attachment_content(self, content_url: str) -> bytes:
        if "sharepoint.com" in content_url or "sharepoint.us" in content_url:
            result = self.download_via_sharing_url(content_url)
            if result:
                return result

        try:
            return self._get_raw(content_url)
        except Exception as e:
            logger.warning(f"Failed to download attachment from {content_url}: {e}")
            return b""

    def list_message_hosted_contents(self, chat_or_team_url: str, message_id: str) -> list:
        url = f"{GRAPH_API_BASE}/{chat_or_team_url}/messages/{message_id}/hostedContents"
        try:
            data = self._get(url)
            return data.get("value", [])
        except Exception as e:
            logger.warning(f"Failed to list hosted contents for message {message_id}: {e}")
            return []

    def download_hosted_content(self, chat_or_team_url: str, message_id: str,
                                 hosted_content_id: str) -> bytes:
        url = f"{GRAPH_API_BASE}/{chat_or_team_url}/messages/{message_id}/hostedContents/{hosted_content_id}/$value"
        try:
            return self._get_raw(url)
        except Exception as e:
            logger.warning(f"Failed to download hosted content: {e}")
            return b""

    def get_meeting_transcript(self, meeting_id: str) -> str:
        try:
            url = f"{GRAPH_API_BASE}/communications/onlineMeetings/{meeting_id}/transcripts"
            data = self._get(url)
            transcripts = data.get("value", [])
            if not transcripts:
                logger.info(f"No transcripts found for meeting {meeting_id}")
                return ""

            transcript_id = transcripts[0].get("id", "")
            if not transcript_id:
                return ""

            content_url = f"{GRAPH_API_BASE}/communications/onlineMeetings/{meeting_id}/transcripts/{transcript_id}/content"
            self._ensure_token()
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "text/vtt",
            }
            response = requests.get(content_url, headers=headers)
            response.raise_for_status()
            return response.text
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (403, 401):
                logger.warning(f"No permission to access transcript for meeting {meeting_id} (need OnlineMeetingTranscript.Read.All)")
            else:
                logger.warning(f"Failed to fetch transcript for meeting {meeting_id}: {e}")
            return ""
        except Exception as e:
            logger.warning(f"Failed to fetch transcript for meeting {meeting_id}: {e}")
            return ""
