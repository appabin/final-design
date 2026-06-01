from fastapi.testclient import TestClient

import app.main as main_module
import app.services.reminder_service as reminder_module
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

        delete = client.delete(f"/api/knowledge/{ingest.json()['doc_id']}")
        assert delete.status_code == 200, delete.text
        delete_payload = delete.json()
        assert delete_payload["deleted"] is True
        assert delete_payload["chunks_deleted"] >= 1

        recent = client.get("/api/knowledge/recent")
        assert recent.status_code == 200
        assert all(item["id"] != ingest.json()["doc_id"] for item in recent.json())

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
        builtin_payload = builtin.json()
        assert builtin_payload["title"] == "检测题"
        assert builtin_payload["markdown_path"].endswith(".md")
        skill_output = client.get(builtin_payload["markdown_url"])
        assert skill_output.status_code == 200
        assert "# 检测题" in skill_output.text

        skill_page = client.get("/tools/skill-result")
        assert skill_page.status_code == 200, skill_page.text
        assert "Hachi Skill 结果" in skill_page.text

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


def test_email_reminder_can_sync_macos_calendar(tmp_path, monkeypatch):
    cfg = Settings(
        hachi_mock_mode=True,
        sqlite_path=str(tmp_path / "calendar_reminder.db"),
        milvus_mode="memory",
        embedding_dim=64,
        workspace_path=str(tmp_path / "workspace"),
        hachi_enable_desktop_notifications=False,
    )
    main_module.settings = cfg

    class Completed:
        returncode = 0
        stdout = "calendar-event-123\n"
        stderr = ""

    def fake_run(args, **kwargs):
        assert args[0] == "osascript"
        assert "Calendar" in args[2]
        return Completed()

    monkeypatch.setattr(reminder_module.sys, "platform", "darwin")
    monkeypatch.setattr(reminder_module.subprocess, "run", fake_run)

    with TestClient(main_module.app) as client:
        skill = client.post(
            "/api/skills/run",
            json={
                "skill_id": "email_reminder",
                "input_text": "主题：同步到日历\n请提醒我检查论文。",
                "metadata": {
                    "reminder_at": "2026-12-01T10:00:00+08:00",
                    "macos_calendar": True,
                    "macos_calendar_name": "Hachi Test",
                },
            },
        )
        assert skill.status_code == 200, skill.text
        reminder = skill.json()["metadata"]["reminder"]
        assert reminder["calendar_event_id"] == "calendar-event-123"
        assert reminder["calendar_error"] is None


def test_thesis_image_inbox_saves_pasted_image(tmp_path):
    cfg = Settings(
        hachi_mock_mode=True,
        sqlite_path=str(tmp_path / "image_inbox.db"),
        milvus_mode="memory",
        embedding_dim=64,
        workspace_path=str(tmp_path / "workspace"),
        thesis_images_path=str(tmp_path / "thesis_images"),
        hachi_enable_desktop_notifications=False,
    )
    main_module.settings = cfg

    png_data_url = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )

    with TestClient(main_module.app) as client:
        page = client.get("/tools/image-inbox")
        assert page.status_code == 200, page.text
        assert "论文图片收集" in page.text

        save = client.post(
            "/api/tools/thesis-image",
            json={
                "image_data_url": png_data_url,
                "name": "skill-markdown-output",
                "caption": "Skill Markdown 输出文件截图",
            },
        )
        assert save.status_code == 200, save.text
        payload = save.json()
        assert payload["file_name"] == "skill-markdown-output.png"
        assert payload["relative_path"] == "images/skill-markdown-output.png"
        assert 'image("images/skill-markdown-output.png", width: 96%)' in payload["typst_snippet"]
        assert "Skill Markdown 输出文件截图" in payload["typst_snippet"]
        assert (tmp_path / "thesis_images" / "skill-markdown-output.png").exists()

        image = client.get(f"/api/tools/thesis-image/{payload['file_name']}")
        assert image.status_code == 200
        assert image.content


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
