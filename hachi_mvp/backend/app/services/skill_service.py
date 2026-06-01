from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import uuid

from ..config import Settings
from ..llm_client import ModelGateway
from ..schemas import SkillRunRequest, SkillRunResponse
from .reminder_service import ReminderService


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    title: str
    instruction: str


BUILTIN_SKILLS: dict[str, SkillDefinition] = {
    "note_summary": SkillDefinition(
        id="note_summary",
        title="笔记摘要",
        instruction=(
            "把输入整理成可复习的笔记。输出包括：一句话结论、核心要点、关键术语、"
            "容易遗漏的细节、后续可追问的问题。保持层级清楚，避免空泛总结。"
        ),
    ),
    "quiz": SkillDefinition(
        id="quiz",
        title="检测题",
        instruction=(
            "基于输入生成一份检测题。包含 5 道选择题、3 道简答题和参考答案。"
            "题目要覆盖概念理解、细节记忆和迁移应用。请使用固定格式："
            "先输出“## 选择题”，每道题用“1. 题干”开头，选项使用“A. / B. / C. / D.”，"
            "并在题后写“答案：A”；再输出“## 简答题”，每道题后写“参考答案：...”；"
            "最后输出“## 评分建议”。"
        ),
    ),
    "flashcards": SkillDefinition(
        id="flashcards",
        title="复习卡片",
        instruction=(
            "把输入拆成 Anki 风格复习卡片。每张卡片包含 Front、Back、Tag。"
            "优先覆盖定义、比较、步骤、原因、易混点和例子。"
        ),
    ),
    "action_plan": SkillDefinition(
        id="action_plan",
        title="行动清单",
        instruction=(
            "把输入转成可执行的行动清单。区分今天可做、需要准备、需要确认、风险点。"
            "每条行动项要具体、可检查，并尽量保留上下文。"
        ),
    ),
    "email_reminder": SkillDefinition(
        id="email_reminder",
        title="邮件提醒",
        instruction="从邮件信息中创建电脑定时提醒。",
    ),
}


class SkillService:
    def __init__(self, *, settings: Settings, models: ModelGateway, reminders: ReminderService):
        self.settings = settings
        self.models = models
        self.reminders = reminders
        self.output_dir = Path(settings.workspace_path) / "skill_outputs"

    async def run(self, req: SkillRunRequest) -> SkillRunResponse:
        skill_id = req.skill_id.strip()
        input_text = req.input_text.strip()
        if not input_text:
            raise ValueError("input_text is empty")

        if skill_id == "email_reminder":
            reminder = self.reminders.create_from_email_skill(
                input_text=input_text,
                metadata=req.metadata,
                title=req.title,
            )
            calendar_line = ""
            if reminder.get("calendar_event_id"):
                calendar_line = f"\n- macOS 日历：已同步（{reminder['calendar_event_id']}）"
            elif reminder.get("calendar_error"):
                calendar_line = f"\n- macOS 日历：同步失败（{reminder['calendar_error']}）"
            result = (
                "已创建邮件定时提醒。\n\n"
                f"- 提醒标题：{reminder['title']}\n"
                f"- 提醒时间：{reminder['remind_at']}\n"
                f"- 提醒内容：{reminder['body']}\n"
                f"- 提醒状态：{reminder['status']}"
                f"{calendar_line}"
            )
            markdown_path, markdown_url = self._write_markdown_output(
                skill_id=skill_id,
                title="邮件提醒",
                result=result,
            )
            return SkillRunResponse(
                skill_id=skill_id,
                title="邮件提醒",
                result=result,
                markdown_path=markdown_path,
                markdown_url=markdown_url,
                metadata={"reminder": reminder},
            )

        if skill_id == "custom":
            instruction = (req.custom_instruction or "").strip()
            if not instruction:
                raise ValueError("custom_instruction is required for custom skill")
            title = (req.title or "自定义 Skill").strip() or "自定义 Skill"
        else:
            skill = BUILTIN_SKILLS.get(skill_id)
            if skill is None:
                raise ValueError(f"Unknown skill_id: {skill_id}")
            instruction = skill.instruction
            title = skill.title

        result = await self.models.run_text_skill(
            skill_title=title,
            instruction=instruction,
            input_text=input_text,
        )
        markdown_path, markdown_url = self._write_markdown_output(
            skill_id=skill_id,
            title=title,
            result=result.strip(),
        )
        return SkillRunResponse(
            skill_id=skill_id,
            title=title,
            result=result.strip(),
            markdown_path=markdown_path,
            markdown_url=markdown_url,
        )

    def _write_markdown_output(self, *, skill_id: str, title: str, result: str) -> tuple[str, str]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_skill_id = re.sub(r"[^A-Za-z0-9_-]+", "-", skill_id).strip("-") or "skill"
        file_name = f"{timestamp}-{safe_skill_id}-{uuid.uuid4().hex[:8]}.md"
        file_path = self.output_dir / file_name
        markdown = f"# {title}\n\n{result.strip()}\n"
        file_path.write_text(markdown, encoding="utf-8")
        return str(file_path), f"/api/skills/outputs/{file_name}"

    def resolve_output_path(self, file_name: str) -> Path:
        if Path(file_name).name != file_name or not file_name.endswith(".md"):
            raise FileNotFoundError(file_name)
        file_path = (self.output_dir / file_name).resolve()
        output_root = self.output_dir.resolve()
        if output_root not in file_path.parents:
            raise FileNotFoundError(file_name)
        if not file_path.exists():
            raise FileNotFoundError(file_name)
        return file_path
