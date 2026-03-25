from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings


def test_ingest_and_ask(tmp_path):
    cfg = Settings(
        hachi_mock_mode=True,
        sqlite_path=str(tmp_path / "api_test.db"),
        milvus_mode="memory",
        embedding_dim=64,
        workspace_path=str(tmp_path / "workspace"),
    )
    main_module.settings = cfg

    with TestClient(main_module.app) as client:
        ingest = client.post(
            "/api/knowledge/text",
            json={
                "title": "Test Doc",
                "content": "LangGraph can orchestrate tools and state in agent workflows.",
            },
        )
        assert ingest.status_code == 200, ingest.text

        ask = client.post(
            "/api/ask",
            json={
                "question": "What does this doc say about LangGraph?",
                "allow_web": False,
                "allow_memory_compress": True,
                "model_mode": "agentic",
            },
        )
        assert ask.status_code == 200, ask.text
        payload = ask.json()
        assert "answer" in payload
        assert "tool_trace" in payload
        assert payload["used_web"] is False

        memory = client.get(f"/api/sessions/{payload['session_id']}/memory")
        assert memory.status_code == 200
        assert (tmp_path / "workspace" / "SOUL.md").exists()
        assert (tmp_path / "workspace" / "MEMORY.md").exists()
