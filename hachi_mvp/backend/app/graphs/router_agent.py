from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from ..llm_client import ModelGateway
from ..tools import AgentTools


class RouterState(TypedDict, total=False):
    question: str
    session_id: str
    allow_web: bool
    allow_memory_compress: bool
    top_k: int
    plan: dict[str, Any]
    local_chunks: list[dict[str, Any]]
    web_results: list[dict[str, Any]]
    memory_notes: list[dict[str, Any]]
    tool_trace: list[dict[str, Any]]
    used_web: bool
    used_memory_compress: bool
    evidence_pack: dict[str, Any]


class RouterAgentGraph:
    def __init__(self, *, tools: AgentTools, models: ModelGateway):
        self.tools = tools
        self.models = models
        self.graph = self._build_graph()

    def _build_graph(self):
        g = StateGraph(RouterState)
        g.add_node("plan", self._plan)
        g.add_node("tool_loop", self._tool_loop)
        g.add_node("evidence_pack", self._evidence_pack)
        g.add_edge(START, "plan")
        g.add_edge("plan", "tool_loop")
        g.add_edge("tool_loop", "evidence_pack")
        g.add_edge("evidence_pack", END)
        return g.compile()

    async def run(self, state: RouterState) -> RouterState:
        return await self.graph.ainvoke(state)

    async def _plan(self, state: RouterState) -> RouterState:
        stats = self.tools.db.get_message_stats(state["session_id"])
        memory_exists = self.tools.db.get_latest_memory_summary(state["session_id"]) is not None
        plan = await self.models.router_plan(
            question=state["question"],
            allow_web=state["allow_web"],
            allow_memory_compress=state["allow_memory_compress"],
            message_count=stats["count"],
            token_count=stats["tokens"],
            memory_exists=memory_exists,
        )
        return {"plan": plan}

    async def _tool_loop(self, state: RouterState) -> RouterState:
        trace: list[dict[str, Any]] = []

        memory_notes = await self.tools.tool_memory_fetch(state["session_id"])
        trace.append(
            {
                "tool": "tool_memory_fetch",
                "status": "ok",
                "memory_count": len(memory_notes),
            }
        )

        dedup: dict[str, dict[str, Any]] = {}
        queries = state["plan"].get("search_queries", [state["question"]])
        for query in queries:
            rows = await self.tools.tool_local_retrieve(query=query, top_k=state["top_k"])
            trace.append(
                {
                    "tool": "tool_local_retrieve",
                    "status": "ok",
                    "query": query,
                    "hit_count": len(rows),
                }
            )
            for row in rows:
                rid = str(row.get("id"))
                if rid not in dedup or float(row.get("score", 0.0)) > float(
                    dedup[rid].get("score", 0.0)
                ):
                    dedup[rid] = row

        local_chunks = sorted(
            list(dedup.values()),
            key=lambda x: float(x.get("score", 0.0)),
            reverse=True,
        )[: state["top_k"]]

        web_results: list[dict[str, Any]] = []
        used_web = False
        if state["plan"].get("need_web_search") and state["allow_web"]:
            web_results = await self.tools.tool_web_search_tavily(
                query=state["question"],
                max_results=5,
            )
            used_web = len(web_results) > 0
            trace.append(
                {
                    "tool": "tool_web_search_tavily",
                    "status": "ok",
                    "hit_count": len(web_results),
                }
            )
        else:
            trace.append(
                {
                    "tool": "tool_web_search_tavily",
                    "status": "skipped",
                }
            )

        used_memory_compress = False
        if state["plan"].get("need_memory_compress") and state["allow_memory_compress"]:
            new_summary = await self.tools.tool_memory_compress(session_id=state["session_id"])
            used_memory_compress = new_summary is not None
            if new_summary:
                memory_notes = [new_summary]
            trace.append(
                {
                    "tool": "tool_memory_compress",
                    "status": "ok" if used_memory_compress else "noop",
                }
            )
        else:
            trace.append(
                {
                    "tool": "tool_memory_compress",
                    "status": "skipped",
                }
            )

        return {
            "local_chunks": local_chunks,
            "web_results": web_results,
            "memory_notes": memory_notes,
            "tool_trace": trace,
            "used_web": used_web,
            "used_memory_compress": used_memory_compress,
        }

    async def _evidence_pack(self, state: RouterState) -> RouterState:
        evidence_pack = {
            "local_chunks": state.get("local_chunks", []),
            "web_results": state.get("web_results", []),
            "memory_notes": state.get("memory_notes", []),
            "tool_trace": state.get("tool_trace", []),
            "router_reason": state.get("plan", {}).get("reason", ""),
        }
        return {"evidence_pack": evidence_pack}
