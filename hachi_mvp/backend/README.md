# Hachi MVP Backend

FastAPI + LangGraph + Milvus + SQLite backend for Hachi Assistant MVP.

## Run

```bash
source /Users/appa/Hachi_Assistant/venv311/bin/activate
cd /Users/appa/Hachi_Assistant/hachi_mvp/backend
pip install -e '.[dev]'
cp .env.example .env
python -m uvicorn app.main:app --reload --port 8008
```

## Quick Scripts

```bash
# 1) Configure backend .env interactively
/Users/appa/Hachi_Assistant/hachi_mvp/scripts/setup_env.sh

# 2) Run backend with /Users/appa/Hachi_Assistant/venv311
/Users/appa/Hachi_Assistant/hachi_mvp/scripts/run_backend.sh

# 3) Start/stop remote Milvus stack (Docker)
/Users/appa/Hachi_Assistant/hachi_mvp/scripts/milvus_remote.sh start
/Users/appa/Hachi_Assistant/hachi_mvp/scripts/milvus_remote.sh status
/Users/appa/Hachi_Assistant/hachi_mvp/scripts/milvus_remote.sh stop
```

## DeepSeek Router example

```env
ROUTER_BASE_URL=https://api.deepseek.com
ROUTER_API_KEY=sk-***
ROUTER_MODEL=deepseek-v4-flash

ANSWER_BASE_URL=https://api.deepseek.com
ANSWER_API_KEY=
ANSWER_MODEL=deepseek-v4-flash
```

`ROUTER_*` is used for pure-text routing, memory compression, and personalization signal analysis.
`ANSWER_*` is used for pure-text answer composition and text skills; when `ANSWER_API_KEY` is empty,
`ROUTER_API_KEY` is reused.
Older `GLM5_ROUTER_*` settings are still supported as a fallback when `ROUTER_*` is not set.

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
- `POST /api/knowledge/page`
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
  - `EMBEDDING_DIM=768` for `tongyi-embedding-vision-flash-2026-03-06`
  - Start Docker Milvus with `scripts/milvus_remote.sh start`
- `MILVUS_MODE=lite` requires `pymilvus[milvus_lite]` and may fail on some macOS/Python setups.
- If Milvus cannot initialize, service falls back to in-memory vectors (non-persistent).
- If you change embedding models, keep `EMBEDDING_DIM` and `MILVUS_COLLECTION` aligned with the vector size.
- Each `ask` now updates `SOUL.md` / `MEMORY.md` from user tone and weak-topic signals, then passes that personalization into final answer generation.
