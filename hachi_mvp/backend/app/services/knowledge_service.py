from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional

from pypdf import PdfReader

from ..config import Settings
from ..db import SQLiteStore
from ..llm_client import ModelGateway
from ..text_utils import chunk_text, sha256_text, utc_now_iso
from ..vector_store import ChunkRecord, VectorStore


class KnowledgeService:
    def __init__(
        self,
        *,
        settings: Settings,
        db: SQLiteStore,
        models: ModelGateway,
        vector_store: VectorStore,
    ):
        self.settings = settings
        self.db = db
        self.models = models
        self.vector_store = vector_store

    async def ingest_text(
        self,
        *,
        title: str,
        content: str,
        source_type: str = "text",
        source_uri: Optional[str] = None,
    ) -> dict:
        return await self._ingest_content(
            title=title,
            source_type=source_type,
            source_uri=source_uri,
            content=content,
        )

    async def ingest_url(self, *, url: str, title: Optional[str] = None) -> dict:
        try:
            import trafilatura
        except ImportError as exc:
            raise RuntimeError("trafilatura is required for URL ingestion") from exc

        downloaded = trafilatura.fetch_url(url)
        extracted = trafilatura.extract(downloaded) if downloaded else None
        if not extracted or not extracted.strip():
            raise ValueError("Unable to extract main content from URL")

        inferred_title = title or url
        return await self._ingest_content(
            title=inferred_title,
            source_type="url",
            source_uri=url,
            content=extracted,
        )

    async def ingest_screenshot(
        self,
        *,
        title: str,
        image_data_url: str,
        source_uri: Optional[str] = None,
        metadata: Optional[dict] = None,
        prompt: Optional[str] = None,
    ) -> dict:
        if not image_data_url.startswith("data:image/"):
            raise ValueError("image_data_url must be a data:image URL")

        analysis = await self.models.describe_screenshot(
            title=title,
            image_data_url=image_data_url,
            page_url=source_uri,
            prompt=prompt,
        )
        content = self._format_screenshot_analysis(
            title=title,
            source_uri=source_uri,
            metadata=metadata or {},
            analysis=analysis,
        )
        return await self._ingest_content(
            title=title,
            source_type="screenshot",
            source_uri=source_uri,
            content=content,
        )

    async def ingest_pdf(self, *, file_path: str, title: Optional[str] = None) -> dict:
        if not os.path.exists(file_path):
            raise FileNotFoundError(file_path)

        reader = PdfReader(file_path)
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        text = "\n\n".join([p.strip() for p in pages if p.strip()]).strip()
        if not text:
            raise ValueError("FAILED_PDF_OCR_REQUIRED")

        inferred_title = title or Path(file_path).name
        return await self._ingest_content(
            title=inferred_title,
            source_type="pdf",
            source_uri=file_path,
            content=text,
        )

    def _format_screenshot_analysis(
        self,
        *,
        title: str,
        source_uri: Optional[str],
        metadata: dict,
        analysis: dict,
    ) -> str:
        lines = [
            f"Screenshot title: {title}",
        ]
        if source_uri:
            lines.append(f"Source URL: {source_uri}")
        captured_at = metadata.get("captured_at")
        if captured_at:
            lines.append(f"Captured at: {captured_at}")

        sections = [
            ("Visual summary", [analysis.get("summary", "")]),
            ("Visible text", analysis.get("visible_text", [])),
            ("Key facts", analysis.get("key_facts", [])),
            ("Entities", analysis.get("entities", [])),
            ("Actions", analysis.get("actions", [])),
        ]
        for heading, values in sections:
            clean_values = [str(value).strip() for value in values if str(value).strip()]
            if not clean_values:
                continue
            lines.append("")
            lines.append(f"{heading}:")
            for value in clean_values:
                lines.append(f"- {value}")

        content = "\n".join(lines).strip()
        if not content:
            raise ValueError("Screenshot analysis is empty")
        return content

    async def _ingest_content(
        self,
        *,
        title: str,
        source_type: str,
        source_uri: Optional[str],
        content: str,
    ) -> dict:
        normalized = content.strip()
        if not normalized:
            raise ValueError("content is empty")

        digest = sha256_text(normalized)
        existing = self.db.find_document_by_hash(digest)
        if existing:
            doc_id = str(existing["id"])
            chunks = self.db.get_document_chunks(doc_id)
            # Rehydrate vectors for current runtime/store to avoid
            # "deduplicated but retrieval empty" after process restarts/fallbacks.
            if chunks:
                embeddings = await self.models.embed_texts([str(c["content"]) for c in chunks])
                now = utc_now_iso()
                vector_rows = []
                for chunk, vec in zip(chunks, embeddings):
                    vector_rows.append(
                        ChunkRecord(
                            id=str(chunk["id"]),
                            doc_id=doc_id,
                            title=str(existing["title"]),
                            source_type=str(existing["source_type"]),
                            content=str(chunk["content"]),
                            vector=vec,
                            created_at=now,
                        )
                    )
                self.vector_store.upsert(vector_rows)
            return {
                "doc_id": doc_id,
                "title": str(existing["title"]),
                "source_type": str(existing["source_type"]),
                "chunks": len(chunks),
                "deduplicated": True,
            }

        chunks = chunk_text(
            normalized,
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
        )
        if not chunks:
            raise ValueError("No chunks generated from content")

        embeddings = await self.models.embed_texts(chunks)
        if len(embeddings) != len(chunks):
            raise RuntimeError("Embedding count mismatch")

        doc_id = str(uuid.uuid4())
        self.db.create_document(
            doc_id=doc_id,
            title=title,
            source_type=source_type,
            source_uri=source_uri,
            content=normalized,
            content_sha256=digest,
        )

        chunk_rows = []
        vector_rows = []
        now = utc_now_iso()
        for index, (chunk, vec) in enumerate(zip(chunks, embeddings)):
            chunk_id = str(uuid.uuid4())
            chunk_rows.append(
                {
                    "id": chunk_id,
                    "doc_id": doc_id,
                    "chunk_index": index,
                    "content": chunk,
                }
            )
            vector_rows.append(
                ChunkRecord(
                    id=chunk_id,
                    doc_id=doc_id,
                    title=title,
                    source_type=source_type,
                    content=chunk,
                    vector=vec,
                    created_at=now,
                )
            )

        self.db.create_chunks(chunk_rows)
        self.vector_store.upsert(vector_rows)

        return {
            "doc_id": doc_id,
            "title": title,
            "source_type": source_type,
            "chunks": len(chunks),
            "deduplicated": False,
        }
