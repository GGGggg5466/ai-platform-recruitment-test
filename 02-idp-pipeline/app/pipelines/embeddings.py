# app/pipelines/embeddings.py
from __future__ import annotations
from typing import List
import httpx
import os

EMBED_URL = os.getenv("WS04_EMBED_URL", "https://ws-04.wade0426.me/embed")

def embed_ws04(texts: List[str]) -> List[List[float]]:
    payload = {
        "texts": texts,
        "task_description": "檢索技術文件",
        "normalize": True,
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.post(EMBED_URL, json=payload)
        r.raise_for_status()
        return r.json()["embeddings"]

def embedding_for_chunk(text: str) -> List[float]:
    # 回傳單一向量
    return embed_ws04([text])[0]