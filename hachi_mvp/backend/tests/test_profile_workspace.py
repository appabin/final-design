from app.profile_workspace import ProfileWorkspace


def test_profile_workspace_records_weak_topic_and_teaching_mode(tmp_path):
    workspace = ProfileWorkspace(str(tmp_path / "workspace"))
    workspace.ensure_files()

    workspace.apply_signal(
        session_id="session-1",
        question="化学词源我还是不懂，能不能简单解释一下",
        signal={
            "tone": "confused",
            "answer_quality_signal": "insufficient",
            "preference_signals": [
                "Prefer simpler explanations with less jargon when the user sounds uncertain.",
            ],
            "weak_topics": [
                {
                    "topic": "化学词源",
                    "reason": "The user sounded uncertain about this topic.",
                    "teaching_strategy": "Start with the date, then define the term, then explain in steps.",
                }
            ],
            "teaching_mode": {
                "simplify": True,
                "step_by_step": True,
                "define_terms": True,
                "use_examples": False,
            },
            "quality_note": "The user message suggests the previous answer was not clear enough.",
        },
    )

    context = workspace.build_personalization_context(
        question="再解释一下化学词源",
        signal={
            "tone": "confused",
            "answer_quality_signal": "insufficient",
            "teaching_mode": {
                "simplify": True,
                "step_by_step": True,
                "define_terms": True,
                "use_examples": False,
            },
        },
    )

    assert context["teaching_mode"]["simplify"] is True
    assert context["teaching_mode"]["step_by_step"] is True
    assert context["matched_weak_topics"]
    assert context["matched_weak_topics"][0]["topic"] == "化学词源"

    soul_text = workspace.soul_path.read_text(encoding="utf-8")
    memory_text = workspace.memory_path.read_text(encoding="utf-8")
    assert "SOUL.md" in soul_text
    assert "化学词源" in memory_text


def test_profile_workspace_normalizes_topic_label_from_question(tmp_path):
    workspace = ProfileWorkspace(str(tmp_path / "workspace"))
    workspace.ensure_files()

    workspace.apply_signal(
        session_id="session-2",
        question="化学一词在中国最早出现在哪，能不能简单一点解释",
        signal={
            "tone": "confused",
            "answer_quality_signal": "insufficient",
            "preference_signals": [],
            "weak_topics": [
                {
                    "topic": "化学一词在中国最早出",
                    "reason": "The topic label should be normalized.",
                    "teaching_strategy": "Use a cleaner topic label.",
                }
            ],
            "teaching_mode": {
                "simplify": True,
                "step_by_step": True,
                "define_terms": True,
                "use_examples": False,
            },
            "quality_note": "",
        },
    )

    memory_text = workspace.memory_path.read_text(encoding="utf-8")
    assert "Topic: 化学一词" in memory_text
    assert "Topic: 化学一词在中国最早出" not in memory_text
