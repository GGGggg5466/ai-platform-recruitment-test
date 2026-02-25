from __future__ import annotations

import os

from apps.common.config import settings
from apps.common.jobs_store import JobsStore
from apps.common.pipeline import run_pipeline_safe
from apps.gateway.hitl.store import HitlStore


jobs_db = JobsStore(db_path=os.path.join(settings.data_dir, "jobs.db"))
hitl_store = HitlStore(db_path=os.path.join(settings.data_dir, "hitl.db"))


async def _process_async(payload: dict):
    return await run_pipeline_safe(payload)


def process_job(payload: dict):
    job_id = payload["job_id"]
    jobs_db.set_status(job_id, "running")

    try:
        import asyncio

        out = asyncio.run(_process_async(payload))

        if out.get("status") == "finished":
            jobs_db.set_status(job_id, "finished", result_json=out)
            return out

        if out.get("status") == "needs_review":
            reason = "|".join(out.get("policy", {}).get("reasons", []) or [out.get("reason", "needs_review")])
            hitl_store.upsert_needs_review(job_id, reason=reason, request_json=payload, draft_response=str(out.get("answer", "")))
            jobs_db.set_status(job_id, "needs_review", result_json=out)
            return out

        jobs_db.set_status(job_id, "failed", error=str(out.get("error", "unknown")), result_json=out)
        return out

    except Exception as e:
        jobs_db.set_status(job_id, "failed", error=str(e))
        raise
