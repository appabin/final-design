from __future__ import annotations

from typing import Any

from ..db import SQLiteStore
from ..llm_client import ModelGateway
from ..profile_workspace import ProfileWorkspace


class PersonalizationService:
    def __init__(
        self,
        *,
        db: SQLiteStore,
        models: ModelGateway,
        workspace: ProfileWorkspace,
    ):
        self.db = db
        self.models = models
        self.workspace = workspace

    async def prepare_context(self, *, session_id: str, question: str) -> dict[str, Any]:
        recent_messages = self.db.get_messages(session_id, limit=8)
        signal = await self.models.analyze_user_signal(
            question=question,
            recent_messages=recent_messages,
        )
        self.workspace.apply_signal(session_id=session_id, question=question, signal=signal)
        return self.workspace.build_personalization_context(question=question, signal=signal)
