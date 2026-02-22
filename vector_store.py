import chromadb
import hashlib
import json
from datetime import datetime, timezone


class VectorStore:
    def __init__(self, persist_dir: str = "./chroma_data"):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name="teams_messages",
            metadata={"hnsw:space": "cosine"},
        )
        self.sync_meta = self.client.get_or_create_collection(
            name="sync_metadata",
            metadata={"hnsw:space": "cosine"},
        )

    def _make_id(self, message: dict) -> str:
        raw = f"{message.get('id', '')}-{message.get('created_at', '')}-{message.get('sender', '')}"
        return hashlib.md5(raw.encode()).hexdigest()

    def add_messages(self, messages: list, team_name: str, channel_name: str) -> int:
        if not messages:
            return 0

        added = 0
        batch_size = 100
        for i in range(0, len(messages), batch_size):
            batch = messages[i : i + batch_size]
            ids = []
            documents = []
            metadatas = []

            for msg in batch:
                doc_id = self._make_id(msg)
                existing = self.collection.get(ids=[doc_id])
                if existing and existing["ids"]:
                    continue

                doc_text = (
                    f"[{msg.get('created_at', 'Unknown time')}] "
                    f"{msg['sender']}: {msg['content']}"
                )

                metadata = {
                    "sender": msg.get("sender", "Unknown"),
                    "created_at": msg.get("created_at", ""),
                    "team": team_name,
                    "channel": channel_name,
                    "message_type": msg.get("message_type", "message"),
                    "message_id": msg.get("id", ""),
                }

                if msg.get("parent_message_id"):
                    metadata["parent_message_id"] = msg["parent_message_id"]

                ids.append(doc_id)
                documents.append(doc_text)
                metadatas.append(metadata)

            if ids:
                self.collection.add(ids=ids, documents=documents, metadatas=metadatas)
                added += len(ids)

        return added

    def search(self, query: str, n_results: int = 20, filters: dict = None) -> list:
        where = None
        if filters:
            conditions = []
            if filters.get("team"):
                conditions.append({"team": {"$eq": filters["team"]}})
            if filters.get("channel"):
                conditions.append({"channel": {"$eq": filters["channel"]}})
            if filters.get("sender"):
                conditions.append({"sender": {"$eq": filters["sender"]}})

            if len(conditions) == 1:
                where = conditions[0]
            elif len(conditions) > 1:
                where = {"$and": conditions}

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=min(n_results, self.collection.count() or 1),
                where=where,
            )
        except Exception:
            results = self.collection.query(
                query_texts=[query],
                n_results=min(n_results, max(self.collection.count(), 1)),
            )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        return [
            {
                "content": doc,
                "metadata": meta,
                "relevance": 1 - dist if dist else 0,
            }
            for doc, meta, dist in zip(documents, metadatas, distances)
        ]

    def get_stats(self) -> dict:
        count = self.collection.count()
        teams = set()
        channels = set()

        if count > 0:
            try:
                sample = self.collection.get(limit=min(count, 1000), include=["metadatas"])
                for meta in sample.get("metadatas", []):
                    if meta.get("team"):
                        teams.add(meta["team"])
                    if meta.get("channel"):
                        channels.add(meta["channel"])
            except Exception:
                pass

        return {
            "total_messages": count,
            "teams": list(teams),
            "channels": list(channels),
        }

    def update_sync_time(self, team_id: str, channel_id: str):
        sync_id = f"sync-{team_id}-{channel_id}"
        now = datetime.now(timezone.utc).isoformat()
        try:
            self.sync_meta.upsert(
                ids=[sync_id],
                documents=[f"Last sync: {now}"],
                metadatas=[{
                    "team_id": team_id,
                    "channel_id": channel_id,
                    "last_sync": now,
                }],
            )
        except Exception:
            pass

    def get_last_sync(self, team_id: str, channel_id: str) -> str:
        sync_id = f"sync-{team_id}-{channel_id}"
        try:
            result = self.sync_meta.get(ids=[sync_id], include=["metadatas"])
            if result and result["metadatas"]:
                return result["metadatas"][0].get("last_sync", "Never")
        except Exception:
            pass
        return "Never"

    def clear_all(self):
        self.client.delete_collection("teams_messages")
        self.collection = self.client.get_or_create_collection(
            name="teams_messages",
            metadata={"hnsw:space": "cosine"},
        )
