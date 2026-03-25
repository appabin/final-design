# Hachi MVP Backend

FastAPI + LangGraph + Milvus + SQLite backend for Hachi Assistant MVP.

## Run

```bash
cd /Users/appa/Hachi_Assistant/hachi_mvp/backend
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
uvicorn app.main:app --reload --port 8008
```

## Quick Scripts

```bash
# 1) Configure backend .env interactively
/Users/appa/Hachi_Assistant/hachi_mvp/scripts/setup_env.sh

# 2) Create venv/install deps/run backend
/Users/appa/Hachi_Assistant/hachi_mvp/scripts/run_backend.sh

# 3) Start/stop remote Milvus stack (Docker)
/Users/appa/Hachi_Assistant/hachi_mvp/scripts/milvus_remote.sh start
/Users/appa/Hachi_Assistant/hachi_mvp/scripts/milvus_remote.sh status
/Users/appa/Hachi_Assistant/hachi_mvp/scripts/milvus_remote.sh stop
```

## DashScope Embedding example

```env
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_API_KEY=sk-***
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIM=1536
EMBEDDING_BATCH_SIZE=10
```

## DashScope MultiModal Embedding example

```env
EMBEDDING_PROVIDER=dashscope_multimodal
EMBEDDING_API_KEY=sk-***
EMBEDDING_MODEL=qwen3-vl-embedding
EMBEDDING_BATCH_SIZE=5
```

## API
- `POST /api/ask`
- `GET /api/models`
- `GET /api/sessions/{id}/memory`
- `POST /api/sessions/{id}/memory/rebuild`
- `POST /api/knowledge/text`
- `POST /api/knowledge/url`
- `POST /api/knowledge/upload`
- `GET /api/knowledge/recent`

## Personalization Workspace
- `WORKSPACE_PATH=./workspace`
- `workspace/SOUL.md`
  - Durable reply style, teaching rules, and learned answer-tuning preferences.
- `workspace/MEMORY.md`
  - Curated weak topics, stable preferences, and answer-quality signals.
- `workspace/memory/YYYY-MM-DD.md`
  - Daily appended interaction observations.

## Notes
- Recommended on macOS:
  - `MILVUS_MODE=remote`
  - `MILVUS_URI=http://127.0.0.1:19530`
  - Start Docker Milvus with `scripts/milvus_remote.sh start`
- `MILVUS_MODE=lite` requires `pymilvus[milvus_lite]` and may fail on some macOS/Python setups.
- If Milvus cannot initialize, service falls back to in-memory vectors (non-persistent).
- Each `ask` now updates `SOUL.md` / `MEMORY.md` from user tone and weak-topic signals, then passes that personalization into final answer generation.
