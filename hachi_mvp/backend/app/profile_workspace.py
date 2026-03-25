from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .text_utils import utc_now_iso

STATE_START = "<!-- HACHI_STATE_START -->"
STATE_END = "<!-- HACHI_STATE_END -->"


def _dedupe_keep_order(values: list[str], limit: int = 12) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        item = str(raw).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def _extract_keywords(text: str) -> list[str]:
    q = (text or "").strip().lower()
    zh_terms = re.findall(r"[\u4e00-\u9fff]{2,8}", q)
    en_terms = re.findall(r"[a-z0-9][a-z0-9\\-]{1,20}", q)
    stopwords = {
        "什么",
        "怎么",
        "如何",
        "为什么",
        "还是",
        "这个",
        "那个",
        "一下",
        "一个",
        "可以",
        "please",
        "what",
        "why",
        "how",
        "about",
        "does",
        "this",
    }
    return _dedupe_keep_order([item for item in zh_terms + en_terms if item not in stopwords], limit=8)


def _normalize_topic_label(topic: str, question: str) -> str:
    candidate = str(topic or "").strip()
    question_text = str(question or "").strip()
    source = candidate or question_text

    if "一词" in question_text:
        match = re.search(r"([\u4e00-\u9fffA-Za-z0-9\\-]{2,12}一词)", question_text)
        if match:
            return match.group(1)

    if "概念" in question_text:
        match = re.search(r"([A-Za-z0-9\\-]{2,24}|[\u4e00-\u9fff]{2,12})\\s*这个?概念", question_text)
        if match:
            return f"{match.group(1)}概念"

    source = re.split(
        r"[，。？?,]|最早|出现在哪|是什么|什么意思|怎么|如何|为什么|能不能|可以|详细|简单|解释一下|解释",
        source,
        maxsplit=1,
    )[0].strip()
    source = re.sub(r"(还是|再|请|帮我|一下)$", "", source).strip()

    if not source:
        source = question_text

    keywords = _extract_keywords(source)
    if keywords:
        return keywords[0]

    return source[:24].strip()


def default_soul_state() -> dict[str, Any]:
    return {
        "core_voice": [
            "Answer with a direct conclusion before the detailed explanation.",
            "Stay calm, concrete, and tutorial-like when the user sounds uncertain.",
            "Do not add unsupported claims beyond the provided evidence pack.",
        ],
        "adaptive_rules": [
            "If the user sounds confused, define the key term first, then expand.",
            "If the user repeats or challenges a point, slow down and break the answer into smaller steps.",
            "When a weak topic is matched, prefer simple wording, explicit transitions, and a tiny example.",
        ],
        "learned_preferences": [],
        "weak_point_policy": [
            "For weak topics, structure the answer as: short answer, term definitions, step-by-step explanation, example.",
            "Keep sentences shorter when the user shows frustration or confusion.",
        ],
        "updated_at": utc_now_iso(),
    }


def default_memory_state() -> dict[str, Any]:
    return {
        "stable_preferences": [],
        "weak_topics": [],
        "quality_signals": [],
        "recent_observations": [],
        "updated_at": utc_now_iso(),
    }


class ProfileWorkspace:
    def __init__(self, workspace_path: str):
        self.root = Path(workspace_path)
        self.soul_path = self.root / "SOUL.md"
        self.memory_path = self.root / "MEMORY.md"
        self.daily_dir = self.root / "memory"

    def ensure_files(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        if not self.soul_path.exists():
            self._save_markdown(self.soul_path, self._render_soul(default_soul_state()))
        if not self.memory_path.exists():
            self._save_markdown(self.memory_path, self._render_memory(default_memory_state()))

    def load_soul_state(self) -> dict[str, Any]:
        return self._load_state(self.soul_path, default_soul_state(), self._render_soul)

    def load_memory_state(self) -> dict[str, Any]:
        return self._load_state(self.memory_path, default_memory_state(), self._render_memory)

    def apply_signal(
        self,
        *,
        session_id: str,
        question: str,
        signal: dict[str, Any],
    ) -> dict[str, Any]:
        soul_state = self.load_soul_state()
        memory_state = self.load_memory_state()
        now = utc_now_iso()

        preference_signals = _dedupe_keep_order(
            [*soul_state.get("learned_preferences", []), *signal.get("preference_signals", [])],
            limit=10,
        )
        soul_state["learned_preferences"] = preference_signals

        adaptive_rules = list(soul_state.get("adaptive_rules", []))
        if signal.get("answer_quality_signal") == "insufficient":
            adaptive_rules.append(
                "If the user's tone implies the last answer was not enough, restate the answer more simply before adding detail."
            )
        if signal.get("teaching_mode", {}).get("step_by_step"):
            adaptive_rules.append(
                "When the user needs help, split the explanation into labeled steps instead of dense paragraphs."
            )
        if signal.get("teaching_mode", {}).get("define_terms"):
            adaptive_rules.append(
                "Define unfamiliar terms in plain language before using them repeatedly."
            )
        soul_state["adaptive_rules"] = _dedupe_keep_order(adaptive_rules, limit=12)
        soul_state["updated_at"] = now

        stable_preferences = list(memory_state.get("stable_preferences", []))
        stable_preferences.extend(signal.get("preference_signals", []))
        memory_state["stable_preferences"] = _dedupe_keep_order(stable_preferences, limit=12)

        weak_topics = list(memory_state.get("weak_topics", []))
        for topic in signal.get("weak_topics", []):
            if not isinstance(topic, dict):
                continue
            topic_name = _normalize_topic_label(str(topic.get("topic", "")).strip(), question)
            if not topic_name:
                continue
            existing = next((item for item in weak_topics if item.get("topic") == topic_name), None)
            if existing is None:
                weak_topics.append(
                    {
                        "topic": topic_name,
                        "keywords": _extract_keywords(topic_name),
                        "reason": str(topic.get("reason", "")).strip(),
                        "teaching_strategy": str(topic.get("teaching_strategy", "")).strip(),
                        "times_seen": 1,
                        "updated_at": now,
                    }
                )
            else:
                existing["reason"] = str(topic.get("reason", existing.get("reason", ""))).strip()
                existing["teaching_strategy"] = str(
                    topic.get("teaching_strategy", existing.get("teaching_strategy", ""))
                ).strip()
                existing["keywords"] = _dedupe_keep_order(
                    [*existing.get("keywords", []), *_extract_keywords(topic_name)],
                    limit=8,
                )
                existing["times_seen"] = int(existing.get("times_seen", 0)) + 1
                existing["updated_at"] = now
        memory_state["weak_topics"] = sorted(
            weak_topics,
            key=lambda item: (int(item.get("times_seen", 0)), str(item.get("updated_at", ""))),
            reverse=True,
        )[:12]

        quality_line = signal.get("quality_note")
        if quality_line:
            quality_signals = list(memory_state.get("quality_signals", []))
            quality_signals.append({"note": str(quality_line), "updated_at": now})
            memory_state["quality_signals"] = quality_signals[-12:]

        recent = list(memory_state.get("recent_observations", []))
        recent.append(
            {
                "at": now,
                "session_id": session_id,
                "question": question[:120],
                "tone": signal.get("tone", "neutral"),
                "answer_quality_signal": signal.get("answer_quality_signal", "unknown"),
            }
        )
        memory_state["recent_observations"] = recent[-12:]
        memory_state["updated_at"] = now

        self._save_markdown(self.soul_path, self._render_soul(soul_state))
        self._save_markdown(self.memory_path, self._render_memory(memory_state))
        self._append_daily_note(session_id=session_id, question=question, signal=signal, now=now)

        return {
            "soul_state": soul_state,
            "memory_state": memory_state,
        }

    def build_personalization_context(
        self,
        *,
        question: str,
        signal: dict[str, Any],
    ) -> dict[str, Any]:
        soul_state = self.load_soul_state()
        memory_state = self.load_memory_state()

        question_keywords = set(_extract_keywords(question))
        matched_weak_topics: list[dict[str, Any]] = []
        for item in memory_state.get("weak_topics", []):
            keywords = {str(keyword).lower() for keyword in item.get("keywords", [])}
            topic_name = str(item.get("topic", "")).lower()
            if topic_name and topic_name in question.lower():
                matched_weak_topics.append(item)
                continue
            if question_keywords and keywords.intersection(question_keywords):
                matched_weak_topics.append(item)

        teaching_mode = signal.get("teaching_mode", {})
        simplify = bool(teaching_mode.get("simplify")) or len(matched_weak_topics) > 0
        step_by_step = bool(teaching_mode.get("step_by_step")) or len(matched_weak_topics) > 0
        define_terms = bool(teaching_mode.get("define_terms")) or len(matched_weak_topics) > 0
        use_examples = bool(teaching_mode.get("use_examples")) or len(matched_weak_topics) > 0

        reply_rules = [
            *soul_state.get("core_voice", []),
            *soul_state.get("adaptive_rules", []),
            *soul_state.get("weak_point_policy", []),
        ]

        return {
            "tone": signal.get("tone", "neutral"),
            "answer_quality_signal": signal.get("answer_quality_signal", "unknown"),
            "reply_rules": _dedupe_keep_order(reply_rules, limit=12),
            "learned_preferences": soul_state.get("learned_preferences", [])[:8],
            "stable_preferences": memory_state.get("stable_preferences", [])[:8],
            "matched_weak_topics": matched_weak_topics[:5],
            "teaching_mode": {
                "simplify": simplify,
                "step_by_step": step_by_step,
                "define_terms": define_terms,
                "use_examples": use_examples,
            },
            "source_files": [
                str(self.soul_path),
                str(self.memory_path),
            ],
        }

    def _append_daily_note(
        self,
        *,
        session_id: str,
        question: str,
        signal: dict[str, Any],
        now: str,
    ) -> None:
        daily_path = self.daily_dir / f"{now[:10]}.md"
        if not daily_path.exists():
            daily_path.write_text(f"# {now[:10]}\n\n", encoding="utf-8")
        weak_topics = ", ".join(
            [str(item.get("topic", "")) for item in signal.get("weak_topics", []) if isinstance(item, dict)]
        ) or "-"
        preference_signals = ", ".join(signal.get("preference_signals", [])) or "-"
        lines = [
            f"## {now}",
            f"- session_id: {session_id}",
            f"- tone: {signal.get('tone', 'neutral')}",
            f"- answer_quality_signal: {signal.get('answer_quality_signal', 'unknown')}",
            f"- question: {question.strip()}",
            f"- weak_topics: {weak_topics}",
            f"- preference_signals: {preference_signals}",
            "",
        ]
        with daily_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines))

    def _load_state(
        self,
        path: Path,
        default_state: dict[str, Any],
        render_fn,
    ) -> dict[str, Any]:
        if not path.exists():
            self._save_markdown(path, render_fn(default_state))
            return default_state
        text = path.read_text(encoding="utf-8")
        match = re.search(f"{re.escape(STATE_START)}\\n(.*?)\\n{re.escape(STATE_END)}", text, flags=re.DOTALL)
        if not match:
            self._save_markdown(path, render_fn(default_state))
            return default_state
        try:
            loaded = json.loads(match.group(1))
        except json.JSONDecodeError:
            self._save_markdown(path, render_fn(default_state))
            return default_state
        if not isinstance(loaded, dict):
            self._save_markdown(path, render_fn(default_state))
            return default_state
        return loaded

    def _render_soul(self, state: dict[str, Any]) -> str:
        content = [
            "# SOUL.md",
            "",
            "This file defines the long-term teaching style and reply tuning for Hachi Assistant.",
            "It follows the OpenClaw-style split: SOUL for durable behavior, MEMORY for curated learned facts.",
            "",
            "## Core Voice",
            *[f"- {item}" for item in state.get("core_voice", [])],
            "",
            "## Adaptive Reply Rules",
            *[f"- {item}" for item in state.get("adaptive_rules", [])],
            "",
            "## Learned User Preferences",
            *([f"- {item}" for item in state.get("learned_preferences", [])] or ["- None yet."]),
            "",
            "## Weak Point Teaching Policy",
            *[f"- {item}" for item in state.get("weak_point_policy", [])],
            "",
            "## Updated At",
            f"- {state.get('updated_at', '')}",
            "",
            STATE_START,
            json.dumps(state, ensure_ascii=False, indent=2),
            STATE_END,
            "",
        ]
        return "\n".join(content)

    def _render_memory(self, state: dict[str, Any]) -> str:
        content = [
            "# MEMORY.md",
            "",
            "Curated long-term memory about the user's learning needs and answer-quality signals.",
            "",
            "## Stable Preferences",
            *([f"- {item}" for item in state.get("stable_preferences", [])] or ["- None yet."]),
            "",
            "## Weak Knowledge Points",
        ]

        weak_topics = state.get("weak_topics", [])
        if weak_topics:
            for item in weak_topics:
                content.extend(
                    [
                        f"- Topic: {item.get('topic', '')}",
                        f"  Reason: {item.get('reason', '') or '-'}",
                        f"  Teaching strategy: {item.get('teaching_strategy', '') or '-'}",
                        f"  Times seen: {item.get('times_seen', 0)}",
                        f"  Updated at: {item.get('updated_at', '')}",
                    ]
                )
        else:
            content.append("- None yet.")

        content.extend(["", "## Answer Quality Signals"])
        quality_signals = state.get("quality_signals", [])
        if quality_signals:
            content.extend(
                [
                    f"- {item.get('updated_at', '')}: {item.get('note', '')}"
                    for item in quality_signals
                    if isinstance(item, dict)
                ]
            )
        else:
            content.append("- None yet.")

        content.extend(["", "## Recent Durable Observations"])
        recent = state.get("recent_observations", [])
        if recent:
            content.extend(
                [
                    f"- {item.get('at', '')}: tone={item.get('tone', 'neutral')}, quality={item.get('answer_quality_signal', 'unknown')}, question={item.get('question', '')}"
                    for item in recent
                    if isinstance(item, dict)
                ]
            )
        else:
            content.append("- None yet.")

        content.extend(
            [
                "",
                "## Updated At",
                f"- {state.get('updated_at', '')}",
                "",
                STATE_START,
                json.dumps(state, ensure_ascii=False, indent=2),
                STATE_END,
                "",
            ]
        )
        return "\n".join(content)

    def _save_markdown(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
