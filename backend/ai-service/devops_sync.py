import re
import logging
from datetime import datetime
from azure_devops_client import AzureDevOpsClient

logger = logging.getLogger(__name__)


def fetch_devops_work_items_as_messages(client: AzureDevOpsClient, devops_project: str,
                                         since: datetime = None) -> list:
    work_item_refs = client.get_work_items(devops_project, since=since)
    if not work_item_refs:
        return []

    ids = [wi["id"] for wi in work_item_refs]
    details = client.get_work_item_details(devops_project, ids)

    messages = []
    for item in details:
        description = item.get("description", "") or ""
        description = re.sub(r"<[^>]+>", " ", description)
        description = re.sub(r"\s+", " ", description).strip()

        acceptance = item.get("acceptance_criteria", "") or ""
        acceptance = re.sub(r"<[^>]+>", " ", acceptance)
        acceptance = re.sub(r"\s+", " ", acceptance).strip()

        repro = item.get("repro_steps", "") or ""
        repro = re.sub(r"<[^>]+>", " ", repro)
        repro = re.sub(r"\s+", " ", repro).strip()

        content_parts = [
            f"[Work Item #{item['id']}] {item.get('title', '')}",
            f"[Type: {item.get('work_item_type', '')}] [State: {item.get('state', '')}]",
            f"[Assigned To: {item.get('assigned_to', 'Unassigned')}]",
            f"[Priority: {item.get('priority', 'N/A')}]",
            f"[Iteration: {item.get('iteration_path', '')}]",
            f"[Area: {item.get('area_path', '')}]",
        ]
        if item.get("tags"):
            content_parts.append(f"[Tags: {item['tags']}]")
        if item.get("story_points"):
            content_parts.append(f"[Story Points: {item['story_points']}]")
        if description:
            content_parts.append(f"Description: {description}")
        if acceptance:
            content_parts.append(f"Acceptance Criteria: {acceptance}")
        if repro:
            content_parts.append(f"Repro Steps: {repro}")

        messages.append({
            "id": f"devops-wi-{item['id']}-{item.get('rev', 0)}",
            "content": "\n".join(content_parts),
            "sender": item.get("created_by", "Unknown"),
            "created_at": item.get("changed_date", item.get("created_date", "")),
            "attachments": [],
            "message_type": "work_item",
        })

        try:
            comments = client.get_work_item_comments(devops_project, item["id"])
            for comment in comments:
                comment_text = comment.get("text", "")
                comment_text = re.sub(r"<[^>]+>", " ", comment_text)
                comment_text = re.sub(r"\s+", " ", comment_text).strip()
                if comment_text:
                    messages.append({
                        "id": f"devops-comment-{item['id']}-{comment.get('id', 0)}",
                        "content": f"[Comment on Work Item #{item['id']}: {item.get('title', '')}] {comment_text}",
                        "sender": comment.get("created_by", "Unknown"),
                        "created_at": comment.get("created_date", ""),
                        "attachments": [],
                        "message_type": "work_item_comment",
                    })
        except Exception as e:
            logger.warning(f"Failed to fetch comments for work item {item['id']}: {e}")

    return messages
