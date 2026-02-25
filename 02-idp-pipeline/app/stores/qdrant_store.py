from __future__ import annotations

import os
import uuid
from typing import List, Dict, Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct


class QdrantStore:
    """
    Real Qdrant store.

    Env:
      - QDRANT_URL (default: http://qdrant:6333)
      - QDRANT_COLLECTION (default: idp_chunks)
    """

    def __init__(self, collection: Optional[str] = None):
        self.url = os.getenv("QDRANT_URL", "http://qdrant:6333")
        self.collection = collection or os.getenv("QDRANT_COLLECTION", "idp_chunks")
        self.client = QdrantClient(url=self.url)

    def _ensure_collection(self, dim: int) -> None:
        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection not in existing:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )

    def upsert(self, vectors: List[List[float]], payloads: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not vectors:
            return {"collection": self.collection, "point_ids": []}

        dim = len(vectors[0])
        self._ensure_collection(dim)

        point_ids = [str(uuid.uuid4()) for _ in vectors]
        points = [
            PointStruct(id=pid, vector=vec, payload=pl)
            for pid, vec, pl in zip(point_ids, vectors, payloads)
        ]

        self.client.upsert(collection_name=self.collection, points=points)
        return {"collection": self.collection, "point_ids": point_ids}