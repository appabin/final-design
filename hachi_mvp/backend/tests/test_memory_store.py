from app.db import SQLiteStore


def test_memory_summary_roundtrip(tmp_path):
    db = SQLiteStore(str(tmp_path / "test.db"))
    db.init_db()

    sid = db.ensure_session("session-1")
    db.upsert_memory_summary(
        session_id=sid,
        facts=["fact1"],
        open_questions=["q1"],
        decisions=["d1"],
        raw_summary="summary",
    )

    row = db.get_latest_memory_summary(sid)
    assert row is not None
    assert row["facts"] == ["fact1"]
    assert row["open_questions"] == ["q1"]
    assert row["decisions"] == ["d1"]
    assert row["raw_summary"] == "summary"
