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


class KnowledgeTextRequest(BaseModel):
    title: str
    content: str


class KnowledgeURLRequest(BaseModel):
    url: str
    title: Optional[str] = None


class KnowledgeIngestResponse(BaseModel):
    doc_id: str
    title: str
    source_type: Literal["text", "url", "pdf"]
    chunks: int
    deduplicated: bool


class ErrorResponse(BaseModel):
    detail: str
