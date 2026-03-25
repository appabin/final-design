from __future__ import annotations

import shutil
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .config import Settings, settings
from .db import SQLiteStore
from .graphs.answer_graph import AnswerGraph
from .graphs.router_agent import RouterAgentGraph
from .llm_client import ModelGateway
from .schemas import (
    AskRequest,
    AskResponse,
    KnowledgeIngestResponse,
    KnowledgeTextRequest,
    KnowledgeURLRequest,
    MemoryRebuildResponse,
    MemorySummaryResponse,
    ModelBindingsResponse,
)
from .services.ask_service import AskService
from .services.knowledge_service import KnowledgeService
from .services.personalization_service import PersonalizationService
from .profile_workspace import ProfileWorkspace
from .tools import AgentTools
from .vector_store import VectorStore


@dataclass
class AppContext:
    settings: Settings
    db: SQLiteStore
    models: ModelGateway
    vector_store: VectorStore
    tools: AgentTools
    ask_service: AskService
    knowledge_service: KnowledgeService
    profile_workspace: ProfileWorkspace
    personalization_service: PersonalizationService


def build_context(cfg: Settings) -> AppContext:
    db = SQLiteStore(cfg.sqlite_path)
    db.init_db()

    vector_store = VectorStore(cfg)
    vector_store.initialize()

    models = ModelGateway(cfg)
    tools = AgentTools(settings=cfg, db=db, vector_store=vector_store, models=models)
    profile_workspace = ProfileWorkspace(cfg.workspace_path)
    profile_workspace.ensure_files()
    personalization_service = PersonalizationService(
        db=db,
        models=models,
        workspace=profile_workspace,
    )

    router_graph = RouterAgentGraph(tools=tools, models=models)
    answer_graph = AnswerGraph(models=models)

    ask_service = AskService(
        settings=cfg,
        db=db,
        tools=tools,
        router_graph=router_graph,
        answer_graph=answer_graph,
        personalization_service=personalization_service,
    )

    knowledge_service = KnowledgeService(
        settings=cfg,
        db=db,
        models=models,
        vector_store=vector_store,
    )

    return AppContext(
        settings=cfg,
        db=db,
        models=models,
        vector_store=vector_store,
        tools=tools,
        ask_service=ask_service,
        knowledge_service=knowledge_service,
        profile_workspace=profile_workspace,
        personalization_service=personalization_service,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ctx = build_context(settings)
    try:
        yield
    finally:
        app.state.ctx.db.close()


app = FastAPI(title="Hachi Assistant MVP", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=FileResponse)
async def index() -> FileResponse:
    frontend_file = Path(__file__).resolve().parents[2] / "frontend" / "index.html"
    if frontend_file.exists():
        return FileResponse(frontend_file)
    raise HTTPException(status_code=404, detail="Frontend not found")


@app.get("/api/models", response_model=ModelBindingsResponse)
async def get_model_bindings() -> ModelBindingsResponse:
    role = app.state.ctx.settings.role_bindings
    return ModelBindingsResponse(
        router=role["router"],
        answer=role["answer"],
        embedding=role["embedding"],
    )


@app.post("/api/ask", response_model=AskResponse)
async def ask(req: AskRequest) -> AskResponse:
    try:
        return await app.state.ctx.ask_service.ask(req)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/sessions/{session_id}/memory", response_model=MemorySummaryResponse)
async def get_memory(session_id: str) -> MemorySummaryResponse:
    try:
        return await app.state.ctx.ask_service.get_memory(session_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/sessions/{session_id}/memory/rebuild", response_model=MemoryRebuildResponse)
async def rebuild_memory(session_id: str) -> MemoryRebuildResponse:
    try:
        summary = await app.state.ctx.ask_service.rebuild_memory(session_id)
        return MemoryRebuildResponse(
            session_id=session_id,
            compressed=summary.has_summary,
            updated_at=summary.updated_at,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/knowledge/text", response_model=KnowledgeIngestResponse)
async def ingest_text(req: KnowledgeTextRequest) -> KnowledgeIngestResponse:
    try:
        result = await app.state.ctx.knowledge_service.ingest_text(
            title=req.title,
            content=req.content,
        )
        return KnowledgeIngestResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/knowledge/url", response_model=KnowledgeIngestResponse)
async def ingest_url(req: KnowledgeURLRequest) -> KnowledgeIngestResponse:
    try:
        result = await app.state.ctx.knowledge_service.ingest_url(
            url=req.url,
            title=req.title,
        )
        return KnowledgeIngestResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/knowledge/upload", response_model=KnowledgeIngestResponse)
async def ingest_upload(file: UploadFile = File(...), title: str | None = None) -> KnowledgeIngestResponse:
    suffix = Path(file.filename or "upload.bin").suffix
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = Path(tmp_file.name)
    try:
        with tmp_file as out:
            shutil.copyfileobj(file.file, out)

        result = await app.state.ctx.knowledge_service.ingest_pdf(
            file_path=str(tmp_path),
            title=title,
        )
        return KnowledgeIngestResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


@app.get("/api/knowledge/recent")
async def list_recent_knowledge(limit: int = 50) -> list[dict[str, object]]:
    safe_limit = max(1, min(200, int(limit)))
    return app.state.ctx.db.list_documents(limit=safe_limit)
