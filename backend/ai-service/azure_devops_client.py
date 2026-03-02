import base64
import logging
import time
import msal
import requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DEVOPS_API_VERSION = "7.0"
DEVOPS_SCOPE = "499b84ac-1321-427f-aa17-267ca6975798/.default"


def _mask(value: str, visible: int = 6) -> str:
    if not value:
        return "(empty)"
    if len(value) <= visible:
        return "***"
    return value[:visible] + "***"


class DevOpsApiError(Exception):
    pass


class AzureDevOpsClient:
    def __init__(self, organization: str, auth_type: str = "pat",
                 pat: str = None, client_id: str = None,
                 client_secret: str = None, tenant_id: str = None):
        self.organization = organization
        self.auth_type = auth_type
        self.pat = pat
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.base_url = f"https://dev.azure.com/{organization}"
        self.access_token = None
        self.token_expiry = 0
        self._msal_app = None

        logger.info(f"[DevOps] Initializing client: org={organization}, auth_type={auth_type}")
        if auth_type == "azure_ad":
            logger.info(f"[DevOps] Azure AD config: tenant_id={_mask(tenant_id or '')}, client_id={_mask(client_id or '')}")
            authority = f"https://login.microsoftonline.com/{self.tenant_id}"
            logger.info(f"[DevOps] Authority URL: {authority}")

        if auth_type == "azure_ad" and client_id and client_secret and tenant_id:
            try:
                self._msal_app = msal.ConfidentialClientApplication(
                    client_id=self.client_id,
                    client_credential=self.client_secret,
                    authority=authority,
                )
                logger.info("[DevOps] MSAL ConfidentialClientApplication created successfully")
            except ValueError as e:
                logger.error(f"[DevOps] MSAL init failed: {e}")
                raise DevOpsApiError(
                    f"Invalid Azure AD Tenant ID '{_mask(tenant_id)}' — "
                    f"tenant not found or unreachable. "
                    f"Verify your Tenant ID in Azure Portal > Azure Active Directory > Overview. "
                    f"Detail: {e}"
                )
        elif auth_type == "pat":
            logger.info(f"[DevOps] PAT auth configured: pat={_mask(pat or '')}")

    def _ensure_token(self):
        if self.auth_type == "pat":
            return
        if self.access_token and time.time() < self.token_expiry - 60:
            logger.debug("[DevOps] Reusing cached Azure AD token")
            return
        if not self._msal_app:
            raise DevOpsApiError("Azure AD auth requires client_id, client_secret, and tenant_id")
        logger.info(f"[DevOps] Acquiring token from Azure AD, scope={DEVOPS_SCOPE}")
        result = self._msal_app.acquire_token_for_client(scopes=[DEVOPS_SCOPE])
        if "access_token" in result:
            self.access_token = result["access_token"]
            self.token_expiry = time.time() + result.get("expires_in", 3600)
            logger.info(f"[DevOps] Token acquired successfully, expires_in={result.get('expires_in', '?')}s, token={_mask(self.access_token)}")
        else:
            error = result.get("error_description", result.get("error", "Unknown error"))
            logger.error(f"[DevOps] Token acquisition FAILED: {result}")
            raise DevOpsApiError(
                f"Azure AD authentication failed — {error}. "
                f"Check your client_id and client_secret are correct."
            )

    def _headers(self):
        if self.auth_type == "pat":
            encoded = base64.b64encode(f":{self.pat}".encode("utf-8")).decode("utf-8")
            logger.debug(f"[DevOps] Using PAT auth: Basic {_mask(encoded)}")
            return {
                "Authorization": f"Basic {encoded}",
                "Content-Type": "application/json",
            }
        else:
            self._ensure_token()
            logger.debug(f"[DevOps] Using Bearer auth: {_mask(self.access_token)}")
            return {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

    def _handle_response_error(self, response, method, url):
        if response.status_code >= 400:
            body = ""
            try:
                body = response.text
            except Exception:
                pass
            logger.error(f"[DevOps] {method} {url} -> HTTP {response.status_code}: {body}")
            if response.status_code == 401:
                raise DevOpsApiError(
                    f"401 Unauthorized for {url}. "
                    f"Response: {body[:500]}. "
                    f"Ensure the service principal / PAT has access to Azure DevOps org '{self.organization}'. "
                    f"For Azure AD: add the app as a user in DevOps Organization Settings > Users. "
                    f"For PAT: verify the token is valid and has 'Work Items (Read)' and 'Project and Team (Read)' scopes."
                )
            elif response.status_code == 403:
                raise DevOpsApiError(
                    f"403 Forbidden for {url}. "
                    f"Response: {body[:500]}. "
                    f"The credentials are valid but lack permissions. "
                    f"Ensure the service principal / user has at least Reader access to the project."
                )
            response.raise_for_status()

    def _get(self, url: str, params: dict = None) -> dict:
        if params is None:
            params = {}
        params.setdefault("api-version", DEVOPS_API_VERSION)
        logger.info(f"[DevOps] GET {url} params={params}")
        response = requests.get(url, headers=self._headers(), params=params)
        logger.info(f"[DevOps] GET {url} -> {response.status_code}")
        self._handle_response_error(response, "GET", url)
        return response.json()

    def _post(self, url: str, json_body: dict = None, params: dict = None) -> dict:
        if params is None:
            params = {}
        params.setdefault("api-version", DEVOPS_API_VERSION)
        logger.info(f"[DevOps] POST {url} params={params} body={json_body}")
        response = requests.post(url, headers=self._headers(), params=params, json=json_body)
        logger.info(f"[DevOps] POST {url} -> {response.status_code}")
        self._handle_response_error(response, "POST", url)
        return response.json()

    def _get_all_pages(self, url: str, params: dict = None, max_pages: int = 50) -> list:
        all_items = []
        page = 0
        if params is None:
            params = {}
        params.setdefault("api-version", DEVOPS_API_VERSION)

        while url and page < max_pages:
            logger.info(f"[DevOps] GET (page {page}) {url} params={params}")
            response = requests.get(
                url,
                headers=self._headers(),
                params=params if page == 0 else {"api-version": DEVOPS_API_VERSION},
            )
            logger.info(f"[DevOps] GET (page {page}) {url} -> {response.status_code}")
            self._handle_response_error(response, "GET", url)
            data = response.json()
            all_items.extend(data.get("value", []))
            continuation_token = response.headers.get("x-ms-continuationtoken")
            if continuation_token:
                if "?" in url:
                    url = url.split("?")[0]
                params = {
                    "api-version": DEVOPS_API_VERSION,
                    "continuationToken": continuation_token,
                }
            else:
                url = None
            page += 1
        logger.info(f"[DevOps] Paginated fetch complete: {len(all_items)} items")
        return all_items

    def get_projects(self) -> list:
        url = f"{self.base_url}/_apis/projects"
        projects = self._get_all_pages(url)
        return [
            {
                "id": p["id"],
                "name": p.get("name", "Unknown"),
                "description": p.get("description", ""),
                "state": p.get("state", ""),
                "url": p.get("url", ""),
            }
            for p in projects
        ]

    def get_work_items(self, project: str, wiql_query: str = None, since: datetime = None) -> list:
        url = f"{self.base_url}/{project}/_apis/wit/wiql"

        if wiql_query is None:
            conditions = ["[System.TeamProject] = @project"]
            if since:
                since_str = since.strftime("%Y-%m-%d")
                conditions.append(f"[System.ChangedDate] >= '{since_str}'")
            where_clause = " AND ".join(conditions)
            wiql_query = f"SELECT [System.Id] FROM WorkItems WHERE {where_clause} ORDER BY [System.ChangedDate] DESC"

        data = self._post(url, json_body={"query": wiql_query})
        work_items = data.get("workItems", [])
        return [{"id": wi["id"], "url": wi.get("url", "")} for wi in work_items]

    def get_work_item_details(self, project: str, ids: list) -> list:
        if not ids:
            return []

        all_details = []
        batch_size = 200
        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i:i + batch_size]
            ids_str = ",".join(str(id_) for id_ in batch_ids)
            url = f"{self.base_url}/{project}/_apis/wit/workitems"
            params = {
                "ids": ids_str,
                "api-version": DEVOPS_API_VERSION,
                "$expand": "all",
            }
            response = requests.get(url, headers=self._headers(), params=params)
            response.raise_for_status()
            data = response.json()
            items = data.get("value", [])

            for item in items:
                fields = item.get("fields", {})
                assigned_to = fields.get("System.AssignedTo", {})
                if isinstance(assigned_to, dict):
                    assigned_to_name = assigned_to.get("displayName", "Unassigned")
                else:
                    assigned_to_name = str(assigned_to) if assigned_to else "Unassigned"

                created_by = fields.get("System.CreatedBy", {})
                if isinstance(created_by, dict):
                    created_by_name = created_by.get("displayName", "Unknown")
                else:
                    created_by_name = str(created_by) if created_by else "Unknown"

                changed_by = fields.get("System.ChangedBy", {})
                if isinstance(changed_by, dict):
                    changed_by_name = changed_by.get("displayName", "Unknown")
                else:
                    changed_by_name = str(changed_by) if changed_by else "Unknown"

                all_details.append({
                    "id": item.get("id"),
                    "rev": item.get("rev"),
                    "url": item.get("url", ""),
                    "title": fields.get("System.Title", ""),
                    "description": fields.get("System.Description", ""),
                    "state": fields.get("System.State", ""),
                    "work_item_type": fields.get("System.WorkItemType", ""),
                    "assigned_to": assigned_to_name,
                    "created_by": created_by_name,
                    "changed_by": changed_by_name,
                    "created_date": fields.get("System.CreatedDate", ""),
                    "changed_date": fields.get("System.ChangedDate", ""),
                    "area_path": fields.get("System.AreaPath", ""),
                    "iteration_path": fields.get("System.IterationPath", ""),
                    "tags": fields.get("System.Tags", ""),
                    "priority": fields.get("Microsoft.VSTS.Common.Priority", 0),
                    "severity": fields.get("Microsoft.VSTS.Common.Severity", ""),
                    "story_points": fields.get("Microsoft.VSTS.Scheduling.StoryPoints"),
                    "remaining_work": fields.get("Microsoft.VSTS.Scheduling.RemainingWork"),
                    "original_estimate": fields.get("Microsoft.VSTS.Scheduling.OriginalEstimate"),
                    "completed_work": fields.get("Microsoft.VSTS.Scheduling.CompletedWork"),
                    "acceptance_criteria": fields.get("Microsoft.VSTS.Common.AcceptanceCriteria", ""),
                    "repro_steps": fields.get("Microsoft.VSTS.TCM.ReproSteps", ""),
                })

        return all_details

    def get_work_item_comments(self, project: str, work_item_id: int) -> list:
        url = f"{self.base_url}/{project}/_apis/wit/workitems/{work_item_id}/comments"
        try:
            data = self._get(url)
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                url_fallback = f"{self.base_url}/{project}/_apis/wit/workitems/{work_item_id}/updates"
                try:
                    updates = self._get_all_pages(url_fallback, max_pages=10)
                    comments = []
                    for update in updates:
                        comment_field = update.get("fields", {}).get("System.History", {})
                        new_value = comment_field.get("newValue", "") if isinstance(comment_field, dict) else ""
                        if new_value and new_value.strip():
                            revised_by = update.get("revisedBy", {})
                            comments.append({
                                "id": update.get("id", 0),
                                "text": new_value,
                                "created_by": revised_by.get("displayName", "Unknown") if isinstance(revised_by, dict) else "Unknown",
                                "created_date": update.get("revisedDate", ""),
                                "work_item_id": work_item_id,
                            })
                    return comments
                except Exception:
                    logger.warning(f"Failed to fetch updates for work item {work_item_id}")
                    return []
            logger.warning(f"Failed to fetch comments for work item {work_item_id}: {e}")
            return []

        comments = data.get("comments", [])
        results = []
        for comment in comments:
            created_by = comment.get("createdBy", {})
            if isinstance(created_by, dict):
                author = created_by.get("displayName", "Unknown")
            else:
                author = "Unknown"

            results.append({
                "id": comment.get("id", 0),
                "text": comment.get("text", ""),
                "created_by": author,
                "created_date": comment.get("createdDate", ""),
                "work_item_id": work_item_id,
            })
        return results

    def get_iterations(self, project: str) -> list:
        url = f"{self.base_url}/{project}/_apis/work/teamsettings/iterations"
        try:
            iterations = self._get_all_pages(url)
        except requests.exceptions.HTTPError as e:
            logger.warning(f"Failed to fetch iterations for project {project}: {e}")
            return []

        results = []
        for iteration in iterations:
            attributes = iteration.get("attributes", {})
            results.append({
                "id": iteration.get("id", ""),
                "name": iteration.get("name", ""),
                "path": iteration.get("path", ""),
                "url": iteration.get("url", ""),
                "start_date": attributes.get("startDate", ""),
                "finish_date": attributes.get("finishDate", ""),
                "time_frame": attributes.get("timeFrame", ""),
            })
        return results

    def get_iteration_work_items(self, project: str, iteration_path: str) -> list:
        escaped_path = iteration_path.replace("'", "''")
        wiql_query = (
            f"SELECT [System.Id] FROM WorkItems "
            f"WHERE [System.TeamProject] = @project "
            f"AND [System.IterationPath] = '{escaped_path}' "
            f"ORDER BY [System.ChangedDate] DESC"
        )
        work_item_refs = self.get_work_items(project, wiql_query=wiql_query)
        if not work_item_refs:
            return []

        ids = [wi["id"] for wi in work_item_refs]
        return self.get_work_item_details(project, ids)
