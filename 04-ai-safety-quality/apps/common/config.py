from __future__ import annotations

import os
from dataclasses import dataclass


def _get(name: str, default: str | None = None) -> str:
    v = os.getenv(name, default)
    if v is None:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "dev")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    queue_name: str = os.getenv("QUEUE_NAME", "default")
    data_dir: str = os.getenv("DATA_DIR", "./data")

    # upstream
    llm_base_url: str = _get("LLM_BASE_URL", "")
    llm_chat_path: str = os.getenv("LLM_CHAT_PATH", "/v1/chat/completions")
    llm_model: str = os.getenv("LLM_MODEL", "")

    vlm_base_url: str = os.getenv("VLM_BASE_URL", "")
    vlm_chat_path: str = os.getenv("VLM_CHAT_PATH", "/v1/chat/completions")
    vlm_model: str = os.getenv("VLM_MODEL", "")

    embed_url: str = _get("EMBED_URL", "")
    embed_model: str = os.getenv("EMBED_MODEL", "")
    embed_dim: int = int(os.getenv("EMBED_DIM", "4096"))

    similarity_url: str = os.getenv("SIMILARITY_URL", "")

    # timeouts & retry
    embed_timeout_s: float = float(os.getenv("EMBED_TIMEOUT_S", "10"))
    llm_timeout_s: float = float(os.getenv("LLM_TIMEOUT_S", "30"))
    vlm_timeout_s: float = float(os.getenv("VLM_TIMEOUT_S", "45"))
    retry_max: int = int(os.getenv("RETRY_MAX", "1"))
    retry_backoff_s: float = float(os.getenv("RETRY_BACKOFF_S", "0.8"))

    # policy thresholds
    risk_block_threshold: float = float(os.getenv("RISK_BLOCK_THRESHOLD", "0.8"))
    confidence_hitl_threshold: float = float(os.getenv("CONFIDENCE_HITL_THRESHOLD", "0.4"))

    # langfuse (optional)
    langfuse_host: str = os.getenv("LANGFUSE_HOST", "")
    langfuse_public_key: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    langfuse_secret_key: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    langfuse_project: str = os.getenv("LANGFUSE_PROJECT", "")


settings = Settings()
