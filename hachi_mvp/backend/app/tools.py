from __future__ import annotations

from typing import Any

import httpx

from .config import Settings
from .db import SQLiteStore
from .llm_client import ModelGateway
from .vector_store import VectorStore


class AgentTools:
    def __init__(
        self,
        *,
        settings: Settings,
        db: SQLiteStore,
        vector_store: VectorStore,
        models: ModelGateway,
    ):
        self.settings = settings
        self.db = db
        self.vector_store = vector_store
        self.models = models

    async def tool_local_retrieve(self, query: str, top_k: int) -> list[dict[str, Any]]:
        query_vec = (await self.models.embed_texts([query]))[0]
        rows = self.vector_store.search(
            query_vector=query_vec,
            top_k=top_k,
            min_score=self.settings.min_score,
        )
        if rows:
            return rows

        # Lexical fallback: helps when vector store is empty/misaligned or low-score.
        fallback = self.db.search_chunks_keyword_fallback(query=query, limit=top_k)
        if not fallback:
            return []

        # Normalize fallback score into [0,1]-like range for downstream ranking.
        max_score = max(float(item.get("score", 0.0)) for item in fallback) or 1.0
        for item in fallback:
            item["score"] = min(1.0, float(item.get("score", 0.0)) / max_score)
        return fallback

    async def tool_web_search_tavily(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        if self.settings.hachi_mock_mode:
            return [
                {
                    "title": "Mock web result",
                    "url": "https://example.com/mock",
                    "snippet": f"Mock web snippet for query: {query}",
                }
            ]

        if not self.settings.tavily_api_key:
            return []

        payload = {
            "api_key": self.settings.tavily_api_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": max_results,
            "include_answer": False,
        }
        timeout = httpx.Timeout(20.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            response = await client.post("https://api.tavily.com/search", json=payload)
            response.raise_for_status()
            data = response.json()

        rows = []
        for item in data.get("results", []):
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "title": str(item.get("title", "Untitled")),
                    "url": item.get("url"),
                    "snippet": str(item.get("content", ""))[:500],
                }
            )
        return rows

    async def tool_memory_fetch(self, session_id: str) -> list[dict[str, Any]]:
        summary = self.db.get_latest_memory_summary(session_id)
        return [summary] if summary else []

    async def tool_memory_compress(self, session_id: str, force: bool = False) -> dict[str, Any] | None:
        stats = self.db.get_message_stats(session_id)
        should_compress = (
            force
            or stats["count"] >= self.settings.memory_max_messages
            or stats["tokens"] >= self.settings.memory_max_tokens
        )
        if not should_compress:
            return None

        messages = self.db.get_messages(session_id, limit=300)
        if not messages:
            return None

        summary = await self.models.compress_memory(messages=messages)
        self.db.upsert_memory_summary(
            session_id=session_id,
            facts=summary.get("facts", []),
            open_questions=summary.get("open_questions", []),
            decisions=summary.get("decisions", []),
            raw_summary=summary.get("raw_summary", ""),
        )
        return self.db.get_latest_memory_summary(session_id)
