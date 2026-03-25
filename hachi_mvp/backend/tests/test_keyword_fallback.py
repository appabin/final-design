from app.db import SQLiteStore


def test_keyword_fallback_can_match_chinese_query(tmp_path):
    db = SQLiteStore(str(tmp_path / "fallback.db"))
    db.init_db()

    doc_id = "doc-1"
    db.create_document(
        doc_id=doc_id,
        title="化学",
        source_type="text",
        source_uri=None,
        content="在中国，化学一词最早出现在1857年的《六合丛谈》。",
        content_sha256="sha-demo",
    )
    db.create_chunks(
        [
            {
                "id": "chunk-1",
                "doc_id": doc_id,
                "chunk_index": 0,
                "content": "在中国，化学一词最早出现在1857年的《六合丛谈》。",
            }
        ]
    )

    rows = db.search_chunks_keyword_fallback("化学一词最早在中国什么时候出现", limit=5)
    assert rows
    assert rows[0]["doc_id"] == doc_id
    assert "1857" in rows[0]["content"]
