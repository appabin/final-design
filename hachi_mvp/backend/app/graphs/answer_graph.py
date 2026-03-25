from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from ..llm_client import ModelGateway


class AnswerState(TypedDict, total=False):
    question: str
    evidence_pack: dict[str, Any]
    answer_payload: dict[str, Any]
    answer: str
    citations: list[dict[str, Any]]


class AnswerGraph:
    def __init__(self, *, models: ModelGateway):
        self.models = models
        self.graph = self._build_graph()

    def _build_graph(self):
        g = StateGraph(AnswerState)
        g.add_node("compose_answer", self._compose_answer)
        g.add_node("citation_format", self._citation_format)
        g.add_node("final_output", self._final_output)
        g.add_edge(START, "compose_answer")
        g.add_edge("compose_answer", "citation_format")
        g.add_edge("citation_format", "final_output")
        g.add_edge("final_output", END)
        return g.compile()

    async def run(self, state: AnswerState) -> AnswerState:
        return await self.graph.ainvoke(state)

    async def _compose_answer(self, state: AnswerState) -> AnswerState:
        payload = await self.models.generate_answer(
            question=state["question"],
            evidence_pack=state["evidence_pack"],
        )
        return {"answer_payload": payload}

    async def _citation_format(self, state: AnswerState) -> AnswerState:
        payload = state.get("answer_payload", {})
        raw_citations = payload.get("citations", [])
        citations: list[dict[str, Any]] = []

        for c in raw_citations:
            if not isinstance(c, dict):
                continue
            source_type = str(c.get("source_type", "local")).lower()
            if source_type not in {"local", "web", "memory"}:
                source_type = "local"
            citations.append(
                {
                    "source_type": source_type,
                    "title": str(c.get("title", "Untitled")),
                    "snippet": str(c.get("snippet", ""))[:320],
                    "url": c.get("url"),
                }
            )

        return {
            "answer": str(payload.get("answer", "")),
            "citations": citations,
        }

    async def _final_output(self, state: AnswerState) -> AnswerState:
        return {
            "answer": state.get("answer", ""),
            "citations": state.get("citations", []),
        }
