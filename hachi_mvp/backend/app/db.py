from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from typing import Any, Optional

from .text_utils import estimate_tokens, utc_now_iso


class SQLiteStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def init_db(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                  id TEXT PRIMARY KEY,
                  title TEXT NOT NULL,
                  source_type TEXT NOT NULL,
                  source_uri TEXT,
                  content TEXT NOT NULL,
                  content_sha256 TEXT NOT NULL UNIQUE,
                  created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chunks (
                  id TEXT PRIMARY KEY,
                  doc_id TEXT NOT NULL,
                  chunk_index INTEGER NOT NULL,
                  content TEXT NOT NULL,
                  token_count INTEGER NOT NULL,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY(doc_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);

                CREATE TABLE IF NOT EXISTS ingestion_jobs (
                  id TEXT PRIMARY KEY,
                  status TEXT NOT NULL,
                  message TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chat_sessions (
                  id TEXT PRIMARY KEY,
                  title TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chat_messages (
                  id TEXT PRIMARY KEY,
                  session_id TEXT NOT NULL,
                  role TEXT NOT NULL,
                  content TEXT NOT NULL,
                  token_estimate INTEGER NOT NULL,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id
                ON chat_messages(session_id, created_at);

                CREATE TABLE IF NOT EXISTS memory_summaries (
                  id TEXT PRIMARY KEY,
                  session_id TEXT NOT NULL,
                  facts_json TEXT NOT NULL,
                  open_questions_json TEXT NOT NULL,
                  decisions_json TEXT NOT NULL,
                  raw_summary TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_memory_summaries_session_id
                ON memory_summaries(session_id, updated_at);

                CREATE TABLE IF NOT EXISTS reminders (
                  id TEXT PRIMARY KEY,
                  title TEXT NOT NULL,
                  body TEXT NOT NULL,
                  remind_at TEXT NOT NULL,
                  remind_at_epoch REAL NOT NULL,
                  source_text TEXT NOT NULL,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  fired_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_reminders_status_time
                ON reminders(status, remind_at_epoch);
                """
            )
            self._conn.commit()

    def ensure_session(self, session_id: Optional[str], title: Optional[str] = None) -> str:
        sid = session_id or str(uuid.uuid4())
        now = utc_now_iso()
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM chat_sessions WHERE id = ?",
                (sid,),
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO chat_sessions(id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (sid, title or "Hachi Session", now, now),
                )
            else:
                self._conn.execute(
                    "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                    (now, sid),
                )
            self._conn.commit()
        return sid

    def add_message(self, session_id: str, role: str, content: str) -> str:
        now = utc_now_iso()
        mid = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                "INSERT INTO chat_messages(id, session_id, role, content, token_estimate, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (mid, session_id, role, content, estimate_tokens(content), now),
            )
            self._conn.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            self._conn.commit()
        return mid

    def get_messages(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, role, content, token_estimate, created_at
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_message_stats(self, session_id: str) -> dict[str, int]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT count(*) as count, coalesce(sum(token_estimate), 0) as tokens
                FROM chat_messages
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        return {"count": int(row["count"]), "tokens": int(row["tokens"])}

    def upsert_memory_summary(
        self,
        session_id: str,
        facts: list[str],
        open_questions: list[str],
        decisions: list[str],
        raw_summary: str,
    ) -> str:
        now = utc_now_iso()
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM memory_summaries WHERE session_id = ? ORDER BY updated_at DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            if row:
                mid = row["id"]
                self._conn.execute(
                    """
                    UPDATE memory_summaries
                    SET facts_json = ?, open_questions_json = ?, decisions_json = ?, raw_summary = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        json.dumps(facts, ensure_ascii=False),
                        json.dumps(open_questions, ensure_ascii=False),
                        json.dumps(decisions, ensure_ascii=False),
                        raw_summary,
                        now,
                        mid,
                    ),
                )
            else:
                mid = str(uuid.uuid4())
                self._conn.execute(
                    """
                    INSERT INTO memory_summaries(
                      id, session_id, facts_json, open_questions_json, decisions_json, raw_summary, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mid,
                        session_id,
                        json.dumps(facts, ensure_ascii=False),
                        json.dumps(open_questions, ensure_ascii=False),
                        json.dumps(decisions, ensure_ascii=False),
                        raw_summary,
                        now,
                        now,
                    ),
                )
            self._conn.commit()
        return mid

    def get_latest_memory_summary(self, session_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT *
                FROM memory_summaries
                WHERE session_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "facts": json.loads(row["facts_json"]),
            "open_questions": json.loads(row["open_questions_json"]),
            "decisions": json.loads(row["decisions_json"]),
            "raw_summary": row["raw_summary"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def find_document_by_hash(self, content_sha256: str) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM documents WHERE content_sha256 = ?",
                (content_sha256,),
            ).fetchone()
        return dict(row) if row else None

    def create_document(
        self,
        doc_id: str,
        title: str,
        source_type: str,
        source_uri: Optional[str],
        content: str,
        content_sha256: str,
    ) -> None:
        now = utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO documents(id, title, source_type, source_uri, content, content_sha256, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (doc_id, title, source_type, source_uri, content, content_sha256, now),
            )
            self._conn.commit()

    def create_chunks(self, rows: list[dict[str, Any]]) -> None:
        now = utc_now_iso()
        with self._lock:
            self._conn.executemany(
                """
                INSERT INTO chunks(id, doc_id, chunk_index, content, token_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        r["id"],
                        r["doc_id"],
                        r["chunk_index"],
                        r["content"],
                        estimate_tokens(r["content"]),
                        now,
                    )
                    for r in rows
                ],
            )
            self._conn.commit()

    def get_document_chunks(self, doc_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM chunks WHERE doc_id = ? ORDER BY chunk_index ASC",
                (doc_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_documents(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT
                  d.id,
                  d.title,
                  d.source_type,
                  d.source_uri,
                  d.created_at,
                  count(c.id) AS chunks
                FROM documents d
                LEFT JOIN chunks c ON c.doc_id = d.id
                GROUP BY d.id
                ORDER BY d.created_at DESC
                LIMIT ?
                """,
                (max(1, limit),),
            ).fetchall()
        return [dict(r) for r in rows]

    def search_chunks_keyword_fallback(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """
        Lightweight lexical fallback when vector retrieval returns empty.
        It scores chunks by keyword overlap and character overlap.
        """
        q = (query or "").strip()
        if not q:
            return []

        with self._lock:
            rows = self._conn.execute(
                """
                SELECT
                  c.id,
                  c.doc_id,
                  c.content,
                  c.created_at,
                  d.title,
                  d.source_type
                FROM chunks c
                JOIN documents d ON d.id = c.doc_id
                ORDER BY c.created_at DESC
                LIMIT 2000
                """
            ).fetchall()

        keyword_candidates: list[str] = []
        zh_phrases = re.findall(r"[\u4e00-\u9fff]{2,}", q)
        en_words = re.findall(r"[A-Za-z0-9]{2,}", q.lower())
        keyword_candidates.extend(zh_phrases)
        keyword_candidates.extend(en_words)

        # Add 2-char shingles for Chinese query to improve match chance.
        for phrase in zh_phrases:
            if len(phrase) > 2:
                for i in range(len(phrase) - 1):
                    keyword_candidates.append(phrase[i : i + 2])

        keywords = []
        seen = set()
        for item in keyword_candidates:
            token = item.strip().lower()
            if token and token not in seen:
                seen.add(token)
                keywords.append(token)
            if len(keywords) >= 30:
                break

        unique_query_chars = {ch for ch in q if not ch.isspace()}
        scored: list[tuple[float, dict[str, Any]]] = []

        for row in rows:
            text = str(row["content"] or "")
            lower = text.lower()
            score = 0.0

            for kw in keywords:
                if kw in lower:
                    score += 1.5 if len(kw) >= 3 else 0.8

            if unique_query_chars:
                overlap = sum(1 for ch in unique_query_chars if ch in text)
                score += overlap / max(1.0, len(unique_query_chars))

            if score <= 0:
                continue

            scored.append(
                (
                    score,
                    {
                        "id": row["id"],
                        "doc_id": row["doc_id"],
                        "title": row["title"],
                        "source_type": row["source_type"],
                        "content": text,
                        "created_at": row["created_at"],
                        "score": score,
                    },
                )
            )

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[: max(1, limit)]]

    def create_reminder(
        self,
        *,
        title: str,
        body: str,
        remind_at: str,
        remind_at_epoch: float,
        source_text: str,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        reminder_id = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO reminders(
                  id, title, body, remind_at, remind_at_epoch, source_text, status, created_at, fired_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reminder_id,
                    title,
                    body,
                    remind_at,
                    float(remind_at_epoch),
                    source_text,
                    "pending",
                    now,
                    None,
                ),
            )
            self._conn.commit()
        return {
            "id": reminder_id,
            "title": title,
            "body": body,
            "remind_at": remind_at,
            "remind_at_epoch": float(remind_at_epoch),
            "source_text": source_text,
            "status": "pending",
            "created_at": now,
            "fired_at": None,
        }

    def list_reminders(self, limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
        safe_limit = max(1, min(200, int(limit)))
        with self._lock:
            if status:
                rows = self._conn.execute(
                    """
                    SELECT *
                    FROM reminders
                    WHERE status = ?
                    ORDER BY remind_at_epoch ASC
                    LIMIT ?
                    """,
                    (status, safe_limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT *
                    FROM reminders
                    ORDER BY
                      CASE status WHEN 'pending' THEN 0 ELSE 1 END,
                      remind_at_epoch ASC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_due_reminders(self, now_epoch: float, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT *
                FROM reminders
                WHERE status = 'pending' AND remind_at_epoch <= ?
                ORDER BY remind_at_epoch ASC
                LIMIT ?
                """,
                (float(now_epoch), max(1, int(limit))),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_reminder_fired(self, reminder_id: str) -> None:
        now = utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                UPDATE reminders
                SET status = 'fired', fired_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (now, reminder_id),
            )
            self._conn.commit()
