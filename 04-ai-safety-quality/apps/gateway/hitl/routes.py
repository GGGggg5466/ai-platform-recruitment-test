from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .store import HitlStore


def build_router(store: HitlStore) -> APIRouter:
    r = APIRouter(prefix="/v1", tags=["hitl"])

    @r.get("/reviews")
    def list_reviews(limit: int = 50):
        items = store.list_needs_review(limit=limit)
        return {
            "items": [
                {
                    "job_id": it.job_id,
                    "status": it.status,
                    "reason": it.reason,
                    "created_at": it.created_at,
                    "updated_at": it.updated_at,
                    "request": it.request_json,
                    "draft_response": it.draft_response,
                }
                for it in items
            ]
        }

    @r.post("/reviews/{job_id}/approve")
    def approve(job_id: str):
        it = store.get(job_id)
        if not it:
            raise HTTPException(status_code=404, detail="review_not_found")
        store.set_status(job_id, "approved")
        return {"job_id": job_id, "status": "approved"}

    @r.post("/reviews/{job_id}/reject")
    def reject(job_id: str):
        it = store.get(job_id)
        if not it:
            raise HTTPException(status_code=404, detail="review_not_found")
        store.set_status(job_id, "rejected")
        return {"job_id": job_id, "status": "rejected"}

    return r
