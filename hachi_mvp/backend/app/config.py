from __future__ import annotations

from pathlib import Path
import warnings

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    hachi_env: str = "dev"
    hachi_host: str = "0.0.0.0"
    hachi_port: int = 8008
    hachi_mock_mode: bool = False

    sqlite_path: str = "./data/hachi_mvp.db"
    milvus_mode: str = "lite"  # lite | remote | memory
    milvus_uri: str = "./data/milvus_lite.db"
    milvus_collection: str = "hachi_chunks"
    workspace_path: str = "./workspace"

    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_provider: str = "auto"  # auto | openai_compatible | dashscope_multimodal
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    embedding_batch_size: int = 10

    glm5_router_base_url: str = ""
    glm5_router_api_key: str = ""
    glm5_router_model: str = "glm-5"

    qwen_answer_base_url: str = ""
    qwen_answer_api_key: str = ""
    qwen_answer_model: str = "qwen3.5-plus"

    tavily_api_key: str = ""

    chunk_size: int = 1000
    chunk_overlap: int = 150
    default_top_k: int = 8
    min_score: float = 0.2

    memory_max_messages: int = 12
    memory_max_tokens: int = 2500

    @property
    def role_bindings(self) -> dict[str, str]:
        return {
            "router": self.glm5_router_model,
            "answer": self.qwen_answer_model,
            "embedding": self.embedding_model,
        }

    def ensure_data_paths(self) -> None:
        base_dir = Path(__file__).resolve().parents[1]

        sqlite_file = Path((self.sqlite_path or "./data/hachi_mvp.db").strip() or "./data/hachi_mvp.db")
        if not sqlite_file.is_absolute():
            sqlite_file = (base_dir / sqlite_file).resolve()
        sqlite_file.parent.mkdir(parents=True, exist_ok=True)
        self.sqlite_path = str(sqlite_file)

        workspace_dir = Path((self.workspace_path or "./workspace").strip() or "./workspace")
        if not workspace_dir.is_absolute():
            workspace_dir = (base_dir / workspace_dir).resolve()
        workspace_dir.mkdir(parents=True, exist_ok=True)
        (workspace_dir / "memory").mkdir(parents=True, exist_ok=True)
        self.workspace_path = str(workspace_dir)

        if self.milvus_mode == "lite":
            raw_milvus_uri = (self.milvus_uri or "").strip()
            if not raw_milvus_uri:
                raw_milvus_uri = "./data/milvus_lite.db"
                warnings.warn(
                    "MILVUS_URI is empty in lite mode, falling back to ./data/milvus_lite.db",
                    RuntimeWarning,
                )
            milvus_file = Path(raw_milvus_uri)
            if not milvus_file.is_absolute():
                milvus_file = (base_dir / milvus_file).resolve()
            milvus_file.parent.mkdir(parents=True, exist_ok=True)
            self.milvus_uri = str(milvus_file)


settings = Settings()
settings.ensure_data_paths()
