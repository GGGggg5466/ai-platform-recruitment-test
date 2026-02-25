from __future__ import annotations

from typing import Any

import numpy as np

from .config import settings
from .circuit_breaker import breaker
from .http_client import post_json_with_retry


class UpstreamError(RuntimeError):
    pass


async def embed_texts(texts: list[str], task_description: str = "Represent this text for retrieval") -> list[list[float]]:
    key = "embed"
    if breaker.is_open(key):
        raise UpstreamError("circuit_open:embed")

    payload: dict[str, Any] = {
        "model": settings.embed_model,
        "texts": texts,
        "task_description": task_description,
        "normalize": True,
    }

    r = await post_json_with_retry(
        settings.embed_url,
        payload,
        timeout_s=settings.embed_timeout_s,
        retry_max=settings.retry_max,
        backoff_s=settings.retry_backoff_s,
    )

    if r.ok and r.json is not None and "embeddings" in r.json:
        breaker.record_success(key)
        embs = r.json["embeddings"]
        # basic shape check
        if not embs or len(embs[0]) != settings.embed_dim:
            raise UpstreamError(f"embed_dim_mismatch expected={settings.embed_dim} got={len(embs[0]) if embs else 'none'}")
        return embs

    breaker.record_failure(key)
    raise UpstreamError(r.error or "embed_failed")


def cosine_sim(a: list[float], b: list[float]) -> float:
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    denom = (np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


async def llm_chat(messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int = 700) -> str:
    key = "llm"
    if breaker.is_open(key):
        raise UpstreamError("circuit_open:llm")

    url = settings.llm_base_url.rstrip("/") + settings.llm_chat_path
    payload: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    r = await post_json_with_retry(
        url,
        payload,
        timeout_s=settings.llm_timeout_s,
        retry_max=settings.retry_max,
        backoff_s=settings.retry_backoff_s,
    )

    if r.ok and r.json is not None:
        breaker.record_success(key)
        try:
            return r.json["choices"][0]["message"]["content"]
        except Exception:
            raise UpstreamError("llm_bad_response")

    breaker.record_failure(key)
    raise UpstreamError(r.error or "llm_failed")
