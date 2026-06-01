from __future__ import annotations

import base64
import re
import shutil
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
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
    KnowledgeDeleteResponse,
    KnowledgeIngestResponse,
    KnowledgeScreenshotRequest,
    KnowledgeTextRequest,
    KnowledgeURLRequest,
    MemoryRebuildResponse,
    MemorySummaryResponse,
    ModelBindingsResponse,
    ReminderResponse,
    SkillRunRequest,
    SkillRunResponse,
    ThesisImageSaveRequest,
    ThesisImageSaveResponse,
)
from .services.ask_service import AskService
from .services.knowledge_service import KnowledgeService
from .services.personalization_service import PersonalizationService
from .services.reminder_service import ReminderService
from .services.skill_service import SkillService
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
    reminder_service: ReminderService
    skill_service: SkillService
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
    reminder_service = ReminderService(settings=cfg, db=db)
    skill_service = SkillService(settings=cfg, models=models, reminders=reminder_service)

    return AppContext(
        settings=cfg,
        db=db,
        models=models,
        vector_store=vector_store,
        tools=tools,
        ask_service=ask_service,
        knowledge_service=knowledge_service,
        reminder_service=reminder_service,
        skill_service=skill_service,
        profile_workspace=profile_workspace,
        personalization_service=personalization_service,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ctx = build_context(settings)
    app.state.ctx.reminder_service.start()
    try:
        yield
    finally:
        await app.state.ctx.reminder_service.stop()
        app.state.ctx.db.close()


app = FastAPI(title="Hachi Assistant", version="1.0.0", lifespan=lifespan)


def translate_exception(exc: Exception) -> HTTPException:
    detail = str(exc)
    lowered = detail.lower()
    if "timeout" in lowered:
        return HTTPException(status_code=504, detail=detail)
    if "connection error" in lowered:
        return HTTPException(status_code=502, detail=detail)
    if "upstream api error" in lowered:
        return HTTPException(status_code=502, detail=detail)
    return HTTPException(status_code=400, detail=detail)


def thesis_images_dir() -> Path:
    configured = app.state.ctx.settings.thesis_images_path.strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = (Path(__file__).resolve().parents[1] / path).resolve()
        return path
    return Path(__file__).resolve().parents[3] / "doc" / "thesis" / "images"


def safe_image_stem(name: str | None) -> str:
    raw = (name or "").strip()
    if raw:
        raw = Path(raw).stem
    if not raw:
        raw = f"pasted-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", raw).strip("-").lower()
    return stem or "pasted-image"


def decode_image_data_url(image_data_url: str) -> tuple[bytes, str]:
    match = re.fullmatch(r"data:image/(png|jpeg|jpg|webp);base64,(.+)", image_data_url.strip(), flags=re.DOTALL)
    if not match:
        raise ValueError("image_data_url must be a png, jpeg, or webp data URL")

    kind = match.group(1).lower()
    extension = "jpg" if kind in {"jpeg", "jpg"} else kind
    try:
        payload = base64.b64decode(match.group(2), validate=True)
    except Exception as exc:
        raise ValueError("image_data_url base64 payload is invalid") from exc
    if not payload:
        raise ValueError("image payload is empty")
    if len(payload) > 20 * 1024 * 1024:
        raise ValueError("image payload is too large")
    return payload, extension


def unique_image_path(directory: Path, stem: str, extension: str, overwrite: bool) -> Path:
    path = directory / f"{stem}.{extension}"
    if overwrite or not path.exists():
        return path
    for index in range(2, 1000):
        candidate = directory / f"{stem}-{index}.{extension}"
        if not candidate.exists():
            return candidate
    raise ValueError("Unable to allocate a unique image file name")


def resolve_thesis_image_path(file_name: str) -> Path:
    if Path(file_name).name != file_name:
        raise FileNotFoundError(file_name)
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.(png|jpg|jpeg|webp)", file_name):
        raise FileNotFoundError(file_name)
    directory = thesis_images_dir().resolve()
    file_path = (directory / file_name).resolve()
    if directory not in file_path.parents or not file_path.exists():
        raise FileNotFoundError(file_name)
    return file_path


def typst_figure_snippet(file_name: str, caption: str | None) -> str:
    caption_text = (caption or Path(file_name).stem).strip() or Path(file_name).stem
    label = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(file_name).stem).strip("-").lower() or "image"
    return (
        "#figure(\n"
        f'  image("images/{file_name}", width: 96%),\n'
        f"  caption: [{caption_text}],\n"
        f")<fig-{label}>"
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=FileResponse)
async def index() -> FileResponse:
    frontend_file = Path(__file__).resolve().parents[2] / "frontend" / "index.html"
    if frontend_file.exists():
        return FileResponse(frontend_file)
    raise HTTPException(status_code=404, detail="Frontend not found")


@app.get("/tools/image-inbox", response_class=FileResponse)
async def image_inbox() -> FileResponse:
    page = Path(__file__).resolve().parents[2] / "frontend" / "image-inbox.html"
    if page.exists():
        return FileResponse(page)
    raise HTTPException(status_code=404, detail="Image inbox page not found")


@app.get("/tools/skill-result", response_class=FileResponse)
async def skill_result_page() -> FileResponse:
    page = Path(__file__).resolve().parents[2] / "frontend" / "skill-result.html"
    if page.exists():
        return FileResponse(page)
    raise HTTPException(status_code=404, detail="Skill result page not found")


@app.get("/api/models", response_model=ModelBindingsResponse)
async def get_model_bindings() -> ModelBindingsResponse:
    role = app.state.ctx.settings.role_bindings
    return ModelBindingsResponse(
        router=role["router"],
        answer=role["answer"],
        embedding=role["embedding"],
    )


@app.post("/api/tools/thesis-image", response_model=ThesisImageSaveResponse)
async def save_thesis_image(req: ThesisImageSaveRequest) -> ThesisImageSaveResponse:
    try:
        payload, extension = decode_image_data_url(req.image_data_url)
        directory = thesis_images_dir()
        directory.mkdir(parents=True, exist_ok=True)
        file_path = unique_image_path(
            directory=directory,
            stem=safe_image_stem(req.name),
            extension=extension,
            overwrite=req.overwrite,
        )
        file_path.write_bytes(payload)
        snippet = typst_figure_snippet(file_path.name, req.caption)
        return ThesisImageSaveResponse(
            file_name=file_path.name,
            path=str(file_path),
            relative_path=f"images/{file_path.name}",
            typst_snippet=snippet,
        )
    except Exception as exc:
        raise translate_exception(exc) from exc


@app.get("/api/tools/thesis-image/{file_name}", response_class=FileResponse)
async def get_thesis_image(file_name: str) -> FileResponse:
    try:
        file_path = resolve_thesis_image_path(file_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Thesis image not found") from exc
    return FileResponse(file_path)


@app.post("/api/ask", response_model=AskResponse)
async def ask(req: AskRequest) -> AskResponse:
    try:
        return await app.state.ctx.ask_service.ask(req)
    except Exception as exc:
        raise translate_exception(exc) from exc


@app.post("/api/skills/run", response_model=SkillRunResponse)
async def run_skill(req: SkillRunRequest) -> SkillRunResponse:
    try:
        return await app.state.ctx.skill_service.run(req)
    except Exception as exc:
        raise translate_exception(exc) from exc


@app.get("/api/skills/outputs/{file_name}", response_class=FileResponse)
async def get_skill_output(file_name: str) -> FileResponse:
    try:
        file_path = app.state.ctx.skill_service.resolve_output_path(file_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Skill output not found") from exc
    return FileResponse(file_path, media_type="text/markdown; charset=utf-8")


@app.get("/api/reminders", response_model=list[ReminderResponse])
async def list_reminders(limit: int = 50, status: str | None = None) -> list[ReminderResponse]:
    reminders = app.state.ctx.reminder_service.list_reminders(limit=limit, status=status)
    return [ReminderResponse(**item) for item in reminders]


@app.get("/api/sessions/{session_id}/memory", response_model=MemorySummaryResponse)
async def get_memory(session_id: str) -> MemorySummaryResponse:
    try:
        return await app.state.ctx.ask_service.get_memory(session_id)
    except Exception as exc:
        raise translate_exception(exc) from exc


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
        raise translate_exception(exc) from exc


@app.post("/api/knowledge/text", response_model=KnowledgeIngestResponse)
async def ingest_text(req: KnowledgeTextRequest) -> KnowledgeIngestResponse:
    try:
        content = req.resolved_content()
        result = await app.state.ctx.knowledge_service.ingest_text(
            title=req.title,
            content=content,
            source_type="text",
            source_uri=req.url,
        )
        return KnowledgeIngestResponse(**result)
    except Exception as exc:
        raise translate_exception(exc) from exc


@app.post("/api/knowledge/page", response_model=KnowledgeIngestResponse)
async def ingest_page(req: KnowledgeTextRequest) -> KnowledgeIngestResponse:
    try:
        content = req.resolved_content()
        result = await app.state.ctx.knowledge_service.ingest_text(
            title=req.title,
            content=content,
            source_type="url" if req.url else "text",
            source_uri=req.url,
        )
        return KnowledgeIngestResponse(**result)
    except Exception as exc:
        raise translate_exception(exc) from exc


@app.post("/api/knowledge/url", response_model=KnowledgeIngestResponse)
async def ingest_url(req: KnowledgeURLRequest) -> KnowledgeIngestResponse:
    try:
        result = await app.state.ctx.knowledge_service.ingest_url(
            url=req.url,
            title=req.title,
        )
        return KnowledgeIngestResponse(**result)
    except Exception as exc:
        raise translate_exception(exc) from exc


@app.post("/api/knowledge/screenshot", response_model=KnowledgeIngestResponse)
async def ingest_screenshot(req: KnowledgeScreenshotRequest) -> KnowledgeIngestResponse:
    try:
        result = await app.state.ctx.knowledge_service.ingest_screenshot(
            title=req.title,
            image_data_url=req.image_data_url,
            source_uri=req.url,
            metadata=req.metadata,
            prompt=req.prompt,
        )
        return KnowledgeIngestResponse(**result)
    except Exception as exc:
        raise translate_exception(exc) from exc


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
        raise translate_exception(exc) from exc
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


@app.get("/api/knowledge/recent")
async def list_recent_knowledge(limit: int = 50) -> list[dict[str, object]]:
    safe_limit = max(1, min(200, int(limit)))
    return app.state.ctx.db.list_documents(limit=safe_limit)


@app.delete("/api/knowledge/{doc_id}", response_model=KnowledgeDeleteResponse)
async def delete_knowledge(doc_id: str) -> KnowledgeDeleteResponse:
    try:
        result = app.state.ctx.knowledge_service.delete_document(doc_id)
        return KnowledgeDeleteResponse(**result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Knowledge document not found") from exc
    except Exception as exc:
        raise translate_exception(exc) from exc
