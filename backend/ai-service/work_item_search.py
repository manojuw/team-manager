import json
import logging

logger = logging.getLogger(__name__)


class WorkItemSearch:
    def __init__(self, openai_client, vector_ops):
        self.openai = openai_client
        self.vector_ops = vector_ops

    def expand_query(self, query: str) -> list:
        try:
            response = self.openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You generate search query variations. "
                            "Given a query (which may be in Hindi, English, or Hinglish), "
                            "produce 4 alternative phrasings in clear English covering different angles, "
                            "synonyms, and perspectives. Respond with JSON only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Original query: {query}\n\n"
                            "Generate 4 alternative search queries for finding related work items. "
                            "Return JSON only: {\"queries\": [\"...\", \"...\", \"...\", \"...\"]}"
                        ),
                    },
                ],
                temperature=0.3,
                max_tokens=200,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)
            variations = data.get("queries", [])
            all_queries = [query] + [q for q in variations if q and q != query]
            return all_queries[:5]
        except Exception as e:
            logger.warning(f"[WorkItemSearch] expand_query error: {e}")
            return [query]

    def search_candidates(self, queries: list, project_id: str, tenant_id: str) -> list:
        seen_ids = set()
        scored = {}

        for q in queries:
            try:
                results = self.vector_ops.search_work_items(q, project_id, tenant_id, n_results=5)
                for r in results:
                    item_id = r.get("id") or r.get("title", "")
                    if not item_id:
                        continue
                    if item_id not in scored:
                        scored[item_id] = r
                        scored[item_id]["_hit_count"] = 1
                    else:
                        scored[item_id]["relevance"] = max(scored[item_id]["relevance"], r["relevance"])
                        scored[item_id]["_hit_count"] += 1
            except Exception as e:
                logger.warning(f"[WorkItemSearch] search_candidates query error for '{q}': {e}")

        candidates = list(scored.values())
        candidates.sort(key=lambda x: (x.get("_hit_count", 0), x.get("relevance", 0)), reverse=True)
        return candidates[:10]

    def resolve_best_match(self, original_query: str, candidates: list) -> dict | None:
        if not candidates:
            return None

        candidates_text = ""
        for i, c in enumerate(candidates):
            candidates_text += (
                f"\n[{i}] Title: {c.get('title', 'N/A')}\n"
                f"     Description: {str(c.get('description', ''))[:200]}\n"
                f"     Source: {c.get('source', 'N/A')}, Relevance: {c.get('relevance', 0):.2f}\n"
            )

        try:
            response = self.openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You match user queries to work items. Be strict — only return a match if it "
                            "genuinely answers the user's question. If none of the candidates are a good match, "
                            "say so clearly. Never force a match. Respond with JSON only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"User asked: {original_query}\n\n"
                            f"Candidate work items:{candidates_text}\n"
                            "Which ONE item best answers the user's question? "
                            "Return JSON only:\n"
                            "{\"found\": true or false, \"index\": <0-based index or null>, "
                            "\"confidence\": \"high\" or \"medium\" or \"low\", "
                            "\"reason\": \"brief explanation\"}"
                        ),
                    },
                ],
                temperature=0,
                max_tokens=150,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)

            if not data.get("found"):
                return None

            confidence = data.get("confidence", "low")
            if confidence == "low":
                logger.info(f"[WorkItemSearch] Low confidence match discarded for query: {original_query}")
                return None

            idx = data.get("index")
            if idx is None or idx < 0 or idx >= len(candidates):
                return None

            result = dict(candidates[idx])
            result["confidence"] = confidence
            result["reason"] = data.get("reason", "")
            return result

        except Exception as e:
            logger.warning(f"[WorkItemSearch] resolve_best_match error: {e}")
            return None

    def find(self, query: str, project_id: str, tenant_id: str) -> dict:
        try:
            queries = self.expand_query(query)
            logger.info(f"[WorkItemSearch] Expanded '{query}' → {len(queries)} queries")

            candidates = self.search_candidates(queries, project_id, tenant_id)
            logger.info(f"[WorkItemSearch] Found {len(candidates)} unique candidates")

            best = self.resolve_best_match(query, candidates)

            if best:
                return {
                    "found": True,
                    "work_item": best,
                    "confidence": best.get("confidence", "medium"),
                    "reason": best.get("reason", ""),
                    "queries_tried": len(queries),
                }
            else:
                return {
                    "found": False,
                    "work_item": None,
                    "confidence": "none",
                    "reason": "No matching work item found in the knowledge base.",
                    "queries_tried": len(queries),
                }
        except Exception as e:
            logger.error(f"[WorkItemSearch] find() error: {e}")
            return {
                "found": False,
                "work_item": None,
                "confidence": "none",
                "reason": "Search error occurred.",
                "queries_tried": 1,
            }
