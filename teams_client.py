import msal
import requests
import time
from datetime import datetime, timezone


GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"


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
        return [{"id": t["id"], "name": t.get("displayName", "Unknown")} for t in teams]

    def get_channels(self, team_id: str) -> list:
        url = f"{GRAPH_API_BASE}/teams/{team_id}/channels"
        channels = self._get_all_pages(url)
        return [
            {
                "id": c["id"],
                "name": c.get("displayName", "Unknown"),
                "description": c.get("description", ""),
            }
            for c in channels
        ]

    def get_channel_messages(
        self, team_id: str, channel_id: str, since: datetime = None, top: int = 50
    ) -> list:
        url = f"{GRAPH_API_BASE}/teams/{team_id}/channels/{channel_id}/messages"
        params = {"$top": top}
        messages = self._get_all_pages(url, params=params, max_pages=10)

        results = []
        for msg in messages:
            created = msg.get("createdDateTime", "")

            is_new_message = True
            if since and created:
                try:
                    msg_time = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if msg_time <= since:
                        is_new_message = False
                except (ValueError, TypeError):
                    pass

            if is_new_message:
                body = msg.get("body", {})
                content = body.get("content", "")
                content_type = body.get("contentType", "text")

                if content_type == "html":
                    import re
                    content = re.sub(r"<[^>]+>", " ", content)
                    content = re.sub(r"\s+", " ", content).strip()

                sender = msg.get("from", {})
                user_info = sender.get("user", {}) if sender else {}
                sender_name = user_info.get("displayName", "Unknown") if user_info else "System"

                attachments = msg.get("attachments", [])
                attachment_info = []
                for att in attachments:
                    attachment_info.append({
                        "name": att.get("name", ""),
                        "content_type": att.get("contentType", ""),
                        "content_url": att.get("contentUrl", ""),
                    })

                if content.strip():
                    results.append({
                        "id": msg.get("id", ""),
                        "content": content,
                        "sender": sender_name,
                        "created_at": created,
                        "attachments": attachment_info,
                        "message_type": msg.get("messageType", "message"),
                    })

            replies = self._get_message_replies(team_id, channel_id, msg.get("id", ""))
            for reply in replies:
                if since and reply.get("created_at"):
                    try:
                        reply_time = datetime.fromisoformat(
                            reply["created_at"].replace("Z", "+00:00")
                        )
                        if reply_time <= since:
                            continue
                    except (ValueError, TypeError):
                        pass
                results.append(reply)

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
                import re
                content = re.sub(r"<[^>]+>", " ", content)
                content = re.sub(r"\s+", " ", content).strip()

            sender = reply.get("from", {})
            user_info = sender.get("user", {}) if sender else {}
            sender_name = user_info.get("displayName", "Unknown") if user_info else "System"

            if content.strip():
                results.append({
                    "id": reply.get("id", ""),
                    "content": content,
                    "sender": sender_name,
                    "created_at": reply.get("createdDateTime", ""),
                    "attachments": [],
                    "message_type": "reply",
                    "parent_message_id": message_id,
                })

        return results

    def get_chat_messages(self, chat_id: str, since: datetime = None, top: int = 50) -> list:
        url = f"{GRAPH_API_BASE}/chats/{chat_id}/messages"
        params = {"$top": top}
        messages = self._get_all_pages(url, params=params, max_pages=10)

        results = []
        for msg in messages:
            created = msg.get("createdDateTime", "")
            if since and created:
                try:
                    msg_time = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if msg_time <= since:
                        continue
                except (ValueError, TypeError):
                    pass

            body = msg.get("body", {})
            content = body.get("content", "")
            content_type = body.get("contentType", "text")

            if content_type == "html":
                import re
                content = re.sub(r"<[^>]+>", " ", content)
                content = re.sub(r"\s+", " ", content).strip()

            sender = msg.get("from", {})
            user_info = sender.get("user", {}) if sender else {}
            sender_name = user_info.get("displayName", "Unknown") if user_info else "System"

            if content.strip():
                results.append({
                    "id": msg.get("id", ""),
                    "content": content,
                    "sender": sender_name,
                    "created_at": created,
                    "attachments": [],
                    "message_type": msg.get("messageType", "message"),
                })

        return results
