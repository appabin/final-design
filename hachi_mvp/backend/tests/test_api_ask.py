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


def test_plugin_payload_compatibility(tmp_path):
    cfg = Settings(
        hachi_mock_mode=True,
        sqlite_path=str(tmp_path / "plugin_payload.db"),
        milvus_mode="memory",
        embedding_dim=64,
        workspace_path=str(tmp_path / "workspace"),
    )
    main_module.settings = cfg

    with TestClient(main_module.app) as client:
        selection_ingest = client.post(
            "/api/knowledge/text",
            json={
                "title": "Selection Capture",
                "text": "Selected text from the browser plugin.",
                "url": "https://example.com/article",
                "source_type": "selection",
                "metadata": {
                    "context_before": "Leading context",
                    "context_after": "Trailing context",
                },
            },
        )
        assert selection_ingest.status_code == 200, selection_ingest.text

        page_ingest = client.post(
            "/api/knowledge/page",
            json={
                "title": "Readable Page",
                "content": "Readable page body extracted by the browser plugin.",
                "url": "https://example.com/article",
                "source_type": "page",
                "metadata": {
                    "site_name": "example.com",
                    "excerpt": "Readable page body",
                },
            },
        )
        assert page_ingest.status_code == 200, page_ingest.text
        payload = page_ingest.json()
        assert payload["source_type"] == "url"


def test_screenshot_ingest_payload(tmp_path):
    cfg = Settings(
        hachi_mock_mode=True,
        sqlite_path=str(tmp_path / "screenshot_payload.db"),
        milvus_mode="memory",
        embedding_dim=64,
        workspace_path=str(tmp_path / "workspace"),
    )
    main_module.settings = cfg

    with TestClient(main_module.app) as client:
        screenshot_ingest = client.post(
            "/api/knowledge/screenshot",
            json={
                "title": "Screenshot Capture",
                "url": "https://example.com/dashboard",
                "image_data_url": (
                    "data:image/jpeg;base64,"
                    "/9j/4AAQSkZJRgABAQAAAQABAAD/2w=="
                ),
                "metadata": {
                    "captured_at": "2026-05-04T00:00:00.000Z",
                    "capture_kind": "visible_tab",
                },
            },
        )
        assert screenshot_ingest.status_code == 200, screenshot_ingest.text
        payload = screenshot_ingest.json()
        assert payload["source_type"] == "screenshot"
        assert payload["chunks"] >= 1


def test_skill_run_builtin_and_custom(tmp_path):
    cfg = Settings(
        hachi_mock_mode=True,
        sqlite_path=str(tmp_path / "skill_test.db"),
        milvus_mode="memory",
        embedding_dim=64,
        workspace_path=str(tmp_path / "workspace"),
        hachi_enable_desktop_notifications=False,
    )
    main_module.settings = cfg

    with TestClient(main_module.app) as client:
        builtin = client.post(
            "/api/skills/run",
            json={
                "skill_id": "quiz",
                "input_text": "LangGraph can orchestrate agent tools and state.",
            },
        )
        assert builtin.status_code == 200, builtin.text
        assert builtin.json()["title"] == "检测题"

        custom = client.post(
            "/api/skills/run",
            json={
                "skill_id": "custom",
                "input_text": "Agent memory needs durable summaries.",
                "custom_instruction": "整理成三条项目 TODO",
            },
        )
        assert custom.status_code == 200, custom.text
        assert custom.json()["title"] == "自定义 Skill"


def test_email_reminder_skill_creates_pending_reminder(tmp_path):
    cfg = Settings(
        hachi_mock_mode=True,
        sqlite_path=str(tmp_path / "email_reminder.db"),
        milvus_mode="memory",
        embedding_dim=64,
        workspace_path=str(tmp_path / "workspace"),
        hachi_enable_desktop_notifications=False,
    )
    main_module.settings = cfg

    with TestClient(main_module.app) as client:
        skill = client.post(
            "/api/skills/run",
            json={
                "skill_id": "email_reminder",
                "input_text": "发件人：导师\n主题：提交论文终稿\n请在截止前回复确认。",
                "metadata": {
                    "reminder_at": "2026-12-01T09:30:00+08:00",
                    "reminder_title": "回复导师论文终稿邮件",
                },
            },
        )
        assert skill.status_code == 200, skill.text
        payload = skill.json()
        assert payload["title"] == "邮件提醒"
        assert payload["metadata"]["reminder"]["status"] == "pending"

        reminders = client.get("/api/reminders?status=pending")
        assert reminders.status_code == 200, reminders.text
        rows = reminders.json()
        assert len(rows) == 1
        assert rows[0]["title"] == "回复导师论文终稿邮件"
        assert rows[0]["status"] == "pending"


def test_ask_timeout_maps_to_504(tmp_path):
    cfg = Settings(
        hachi_mock_mode=True,
        sqlite_path=str(tmp_path / "timeout_test.db"),
        milvus_mode="memory",
        embedding_dim=64,
        workspace_path=str(tmp_path / "workspace"),
    )
    main_module.settings = cfg

    with TestClient(main_module.app) as client:
        async def _raise_timeout(_req):
            raise ValueError("Upstream API timeout on glm-5 router call. Please retry.")

        client.app.state.ctx.ask_service.ask = _raise_timeout

        ask = client.post(
            "/api/ask",
            json={
                "question": "Will this timeout?",
                "allow_web": False,
                "allow_memory_compress": False,
                "model_mode": "agentic",
            },
        )
        assert ask.status_code == 504, ask.text
        assert "timeout" in ask.json()["detail"].lower()
