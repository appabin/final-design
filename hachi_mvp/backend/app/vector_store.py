from __future__ import annotations

import math
import os
import sys
import warnings
from dataclasses import dataclass
from typing import Any, Optional

from .config import Settings


@dataclass
class ChunkRecord:
    id: str
    doc_id: str
    title: str
    source_type: str
    content: str
    vector: list[float]
    created_at: str


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


class InMemoryVectorStore:
    def __init__(self):
        self.records: dict[str, ChunkRecord] = {}

    def initialize(self) -> None:
        return

    def upsert(self, records: list[ChunkRecord]) -> None:
        for record in records:
            self.records[record.id] = record

    def search(self, query_vector: list[float], top_k: int, min_score: float) -> list[dict[str, Any]]:
        scored = []
        for record in self.records.values():
            score = _cosine_similarity(query_vector, record.vector)
            if score >= min_score:
                scored.append((score, record))
        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, record in scored[:top_k]:
            results.append(
                {
                    "id": record.id,
                    "doc_id": record.doc_id,
                    "title": record.title,
                    "source_type": record.source_type,
                    "content": record.content,
                    "score": score,
                    "created_at": record.created_at,
                }
            )
        return results

    def delete_doc(self, doc_id: str) -> None:
        to_delete = [rid for rid, rec in self.records.items() if rec.doc_id == doc_id]
        for rid in to_delete:
            del self.records[rid]


class MilvusVectorStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.collection = settings.milvus_collection
        self.dimension = settings.embedding_dim
        self._enabled = settings.milvus_mode in {"lite", "remote"}
        self._fallback = InMemoryVectorStore()
        self._client = None

    def _collection_vector_dim(self) -> Optional[int]:
        if self._client is None:
            return None

        description = self._client.describe_collection(collection_name=self.collection)
        fields = description.get("fields", [])
        for field in fields:
            if field.get("name") != "vector":
                continue
            params = field.get("params", {})
            dim = params.get("dim")
            return int(dim) if dim is not None else None
        return None

    def initialize(self) -> None:
        if not self._enabled:
            self._fallback.initialize()
            return

        # milvus-lite currently has instability on some local environments:
        # - Python 3.13
        # - macOS + grpc dns:/// target issue (startup hang)
        # Keep service available by falling back to in-memory store.
        skip_lite_on_macos = os.getenv("HACHI_FORCE_MILVUS_LITE", "").lower() not in {"1", "true", "yes"}
        if self.settings.milvus_mode == "lite" and (
            sys.version_info >= (3, 13) or (sys.platform == "darwin" and skip_lite_on_macos)
        ):
            self._client = None
            self._fallback.initialize()
            if sys.version_info >= (3, 13):
                warnings.warn(
                    "Python 3.13 detected: skipping milvus-lite initialization due compatibility issue. "
                    "Using in-memory vector store (non-persistent). For persistent local vectors, run with Python 3.11/3.12.",
                    RuntimeWarning,
                )
            else:
                warnings.warn(
                    "macOS detected with milvus-lite mode: skipping milvus-lite initialization due known gRPC "
                    "dns:/// compatibility issue on some local setups. "
                    "Using in-memory vector store (non-persistent). "
                    "Set HACHI_FORCE_MILVUS_LITE=1 to force lite startup.",
                    RuntimeWarning,
                )
            return

        try:
            from pymilvus import DataType, MilvusClient

            self._client = MilvusClient(uri=self.settings.milvus_uri)
            has = self._client.has_collection(collection_name=self.collection)
            if not has:
                schema = self._client.create_schema(auto_id=False, enable_dynamic_field=True)
                schema.add_field(
                    field_name="id",
                    datatype=DataType.VARCHAR,
                    is_primary=True,
                    max_length=128,
                )
                schema.add_field(
                    field_name="vector",
                    datatype=DataType.FLOAT_VECTOR,
                    dim=self.dimension,
                )
                index_params = self._client.prepare_index_params()
                index_params.add_index(
                    field_name="vector",
                    metric_type="COSINE",
                    index_type="AUTOINDEX",
                )
                self._client.create_collection(
                    collection_name=self.collection,
                    schema=schema,
                    index_params=index_params,
                )
            else:
                existing_dim = self._collection_vector_dim()
                if existing_dim is not None and existing_dim != self.dimension:
                    raise RuntimeError(
                        "Milvus collection dimension mismatch: "
                        f"collection={self.collection} schema_dim={existing_dim} "
                        f"embedding_dim={self.dimension}. "
                        "Use a new MILVUS_COLLECTION or align EMBEDDING_DIM with the model output."
                    )
        except RuntimeError:
            raise
        except Exception as exc:
            # If Milvus init fails, keep service available with in-memory fallback.
            self._client = None
            self._fallback.initialize()
            warnings.warn(
                "Milvus lite initialization failed "
                f"({type(exc).__name__}: {exc}). "
                "Falling back to in-memory vector store; vectors are not persistent.",
                RuntimeWarning,
            )

    def upsert(self, records: list[ChunkRecord]) -> None:
        if self._client is None:
            self._fallback.upsert(records)
            return

        for record in records:
            if len(record.vector) != self.dimension:
                raise RuntimeError(
                    "Embedding dimension mismatch before Milvus upsert: "
                    f"expected={self.dimension} actual={len(record.vector)} "
                    f"collection={self.collection}"
                )

        data = []
        for rec in records:
            data.append(
                {
                    "id": rec.id,
                    "vector": rec.vector,
                    "doc_id": rec.doc_id,
                    "title": rec.title,
                    "source_type": rec.source_type,
                    "content": rec.content,
                    "created_at": rec.created_at,
                }
            )
        try:
            self._client.upsert(collection_name=self.collection, data=data)
        except Exception as exc:
            raise RuntimeError(
                f"Milvus upsert failed for collection={self.collection}: {type(exc).__name__}: {exc}"
            ) from exc

    def search(self, query_vector: list[float], top_k: int, min_score: float) -> list[dict[str, Any]]:
        if self._client is None:
            return self._fallback.search(query_vector, top_k, min_score)

        try:
            result = self._client.search(
                collection_name=self.collection,
                data=[query_vector],
                anns_field="vector",
                limit=top_k,
                output_fields=["doc_id", "title", "source_type", "content", "created_at"],
            )
        except Exception:
            return self._fallback.search(query_vector, top_k, min_score)

        rows = result[0] if result else []
        parsed: list[dict[str, Any]] = []
        for row in rows:
            score = float(row.get("distance", 0.0))
            if score < min_score:
                continue
            entity = row.get("entity", {})
            parsed.append(
                {
                    "id": row.get("id"),
                    "doc_id": entity.get("doc_id"),
                    "title": entity.get("title", "Untitled"),
                    "source_type": entity.get("source_type", "text"),
                    "content": entity.get("content", ""),
                    "score": score,
                    "created_at": entity.get("created_at", ""),
                }
            )
        return parsed

    def delete_doc(self, doc_id: str) -> None:
        if self._client is None:
            self._fallback.delete_doc(doc_id)
            return

        expr = f'doc_id == "{doc_id}"'
        try:
            self._client.delete(collection_name=self.collection, filter=expr)
        except Exception:
            self._fallback.delete_doc(doc_id)


class VectorStore:
    def __init__(self, settings: Settings):
        self.impl: MilvusVectorStore | InMemoryVectorStore
        if settings.milvus_mode == "memory":
            self.impl = InMemoryVectorStore()
        else:
            self.impl = MilvusVectorStore(settings)

    def initialize(self) -> None:
        self.impl.initialize()

    def upsert(self, records: list[ChunkRecord]) -> None:
        self.impl.upsert(records)

    def search(self, query_vector: list[float], top_k: int, min_score: float) -> list[dict[str, Any]]:
        return self.impl.search(query_vector, top_k, min_score)

    def delete_doc(self, doc_id: str) -> None:
        self.impl.delete_doc(doc_id)
