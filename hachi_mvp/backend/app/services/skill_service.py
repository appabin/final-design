from __future__ import annotations

from dataclasses import dataclass

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
            "题目要覆盖概念理解、细节记忆和迁移应用，最后给出评分建议。"
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
    def __init__(self, *, models: ModelGateway, reminders: ReminderService):
        self.models = models
        self.reminders = reminders

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
            result = (
                "已创建邮件定时提醒。\n\n"
                f"- 提醒标题：{reminder['title']}\n"
                f"- 提醒时间：{reminder['remind_at']}\n"
                f"- 提醒内容：{reminder['body']}\n"
                f"- 提醒状态：{reminder['status']}"
            )
            return SkillRunResponse(
                skill_id=skill_id,
                title="邮件提醒",
                result=result,
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
        return SkillRunResponse(
            skill_id=skill_id,
            title=title,
            result=result.strip(),
        )
