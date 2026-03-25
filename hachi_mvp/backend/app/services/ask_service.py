from __future__ import annotations

from ..config import Settings
from ..db import SQLiteStore
from ..graphs.answer_graph import AnswerGraph
from ..graphs.router_agent import RouterAgentGraph
from ..schemas import AskRequest, AskResponse, MemorySummaryResponse
from .personalization_service import PersonalizationService
from ..tools import AgentTools


class AskService:
    def __init__(
        self,
        *,
        settings: Settings,
        db: SQLiteStore,
        tools: AgentTools,
        router_graph: RouterAgentGraph,
        answer_graph: AnswerGraph,
        personalization_service: PersonalizationService,
    ):
        self.settings = settings
        self.db = db
        self.tools = tools
        self.router_graph = router_graph
        self.answer_graph = answer_graph
        self.personalization_service = personalization_service

    async def ask(self, req: AskRequest) -> AskResponse:
        session_id = self.db.ensure_session(req.session_id)
        self.db.add_message(session_id, "user", req.question)
        personalization = await self.personalization_service.prepare_context(
            session_id=session_id,
            question=req.question,
        )

        router_state = await self.router_graph.run(
            {
                "question": req.question,
                "session_id": session_id,
                "allow_web": req.allow_web,
                "allow_memory_compress": req.allow_memory_compress,
                "top_k": req.top_k or self.settings.default_top_k,
            }
        )
        evidence_pack = dict(router_state.get("evidence_pack", {}))
        evidence_pack["personalization"] = personalization

        answer_state = await self.answer_graph.run(
            {
                "question": req.question,
                "evidence_pack": evidence_pack,
            }
        )

        answer = answer_state.get("answer", "")
        citations = answer_state.get("citations", [])
        self.db.add_message(session_id, "assistant", answer)

        return AskResponse(
            session_id=session_id,
            answer=answer,
            citations=citations,
            tool_trace=router_state.get("tool_trace", []),
            used_web=bool(router_state.get("used_web", False)),
            used_memory_compress=bool(router_state.get("used_memory_compress", False)),
        )

    async def get_memory(self, session_id: str) -> MemorySummaryResponse:
        session_id = self.db.ensure_session(session_id)
        summary = self.db.get_latest_memory_summary(session_id)
        if not summary:
            return MemorySummaryResponse(session_id=session_id, has_summary=False)

        return MemorySummaryResponse(
            session_id=session_id,
            has_summary=True,
            updated_at=summary.get("updated_at"),
            facts=summary.get("facts", []),
            open_questions=summary.get("open_questions", []),
            decisions=summary.get("decisions", []),
            raw_summary=summary.get("raw_summary", ""),
        )

    async def rebuild_memory(self, session_id: str) -> MemorySummaryResponse:
        session_id = self.db.ensure_session(session_id)
        await self.tools.tool_memory_compress(session_id=session_id, force=True)
        return await self.get_memory(session_id)
