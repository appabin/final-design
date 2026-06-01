from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class Citation(BaseModel):
    source_type: Literal["local", "web", "memory"]
    title: str
    snippet: str
    url: Optional[str] = None


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    model_mode: Literal["agentic"] = "agentic"
    allow_web: bool = True
    allow_memory_compress: bool = True
    top_k: Optional[int] = Field(default=None, ge=1, le=50)


class AskResponse(BaseModel):
    session_id: str
    answer: str
    citations: list[Citation]
    tool_trace: list[dict[str, Any]]
    used_web: bool
    used_memory_compress: bool


class MemorySummaryResponse(BaseModel):
    session_id: str
    has_summary: bool
    updated_at: Optional[str] = None
    facts: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    raw_summary: str = ""


class MemoryRebuildResponse(BaseModel):
    session_id: str
    compressed: bool
    updated_at: Optional[str] = None


class ModelBindingsResponse(BaseModel):
    router: str
    answer: str
    embedding: str


class SkillRunRequest(BaseModel):
    skill_id: str
    input_text: str = Field(..., min_length=1)
    title: Optional[str] = None
    custom_instruction: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillRunResponse(BaseModel):
    skill_id: str
    title: str
    result: str
    markdown_path: Optional[str] = None
    markdown_url: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReminderResponse(BaseModel):
    id: str
    title: str
    body: str
    remind_at: str
    status: Literal["pending", "fired"]
    created_at: str
    fired_at: Optional[str] = None
    source_text: str = ""
    calendar_event_id: Optional[str] = None
    calendar_error: Optional[str] = None


class KnowledgeTextRequest(BaseModel):
    title: str
    content: Optional[str] = None
    text: Optional[str] = None
    url: Optional[str] = None
    source_type: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def resolved_content(self) -> str:
        return (self.content or self.text or "").strip()


class KnowledgeURLRequest(BaseModel):
    url: str
    title: Optional[str] = None


class KnowledgeScreenshotRequest(BaseModel):
    title: str
    image_data_url: str = Field(..., min_length=32)
    url: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    prompt: Optional[str] = None


class KnowledgeIngestResponse(BaseModel):
    doc_id: str
    title: str
    source_type: Literal["text", "url", "pdf", "screenshot"]
    chunks: int
    deduplicated: bool


class KnowledgeDeleteResponse(BaseModel):
    doc_id: str
    title: str
    deleted: bool
    chunks_deleted: int


class ThesisImageSaveRequest(BaseModel):
    image_data_url: str = Field(..., min_length=32)
    name: Optional[str] = None
    caption: Optional[str] = None
    overwrite: bool = False


class ThesisImageSaveResponse(BaseModel):
    file_name: str
    path: str
    relative_path: str
    typst_snippet: str


class ErrorResponse(BaseModel):
    detail: str
