from __future__ import annotations
import os, json, uuid, time, hashlib
from redis import Redis
from rq import Queue
from rq.job import Job
from typing import Optional

from app.core.config import REDIS_URL, RQ_QUEUE, DATA_DIR
from app.core.schemas import JobStatusResponse, StoreRefs, JobArtifacts, QualityReport, RouteTraceItem
from app.worker_tasks import process_job

def _redis() -> Redis:
    return Redis.from_url(REDIS_URL)

def enqueue_job(filename: str, content: bytes, route: str) -> str:
    job_id = str(uuid.uuid4())
    job_dir = os.path.join(DATA_DIR, "jobs", job_id)
    os.makedirs(job_dir, exist_ok=True)

    # persist input
    input_path = os.path.join(job_dir, filename)
    with open(input_path, "wb") as f:
        f.write(content)

    meta = {"filename": filename, "route": route, "input_path": input_path}
    with open(os.path.join(job_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    q = Queue(RQ_QUEUE, connection=_redis())
    q.enqueue(process_job, job_id, meta, job_id=job_id)
    return job_id

def get_job_result(job_id: str) -> JobStatusResponse:
    q = Queue(RQ_QUEUE, connection=_redis())
    try:
        job = Job.fetch(job_id, connection=_redis())
    except Exception:
        # Not found in RQ yet; see if result exists
        job = None

    job_dir = os.path.join(DATA_DIR, "jobs", job_id)
    result_path = os.path.join(job_dir, "result.json")
    quality_path = os.path.join(job_dir, "quality.json")
    lineage_path = os.path.join(job_dir, "lineage.json")
    md_path = os.path.join(job_dir, "result.md")

    if os.path.exists(result_path):
        with open(result_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        status = payload.get("status", "finished")
        return JobStatusResponse(
            job_id=job_id,
            status=status,
            chosen_route=payload.get("chosen_route"),
            route_trace=[RouteTraceItem(**x) for x in payload.get("route_trace", [])],
            quality_report=QualityReport(**payload.get("quality_report")) if payload.get("quality_report") else None,
            stores=StoreRefs(**payload.get("stores", {})),
            artifacts=JobArtifacts(
                result_json_path=result_path,
                result_md_path=md_path if os.path.exists(md_path) else None,
                lineage_path=lineage_path if os.path.exists(lineage_path) else None,
                quality_path=quality_path if os.path.exists(quality_path) else None,
            ),
            error=payload.get("error"),
        )

    # If not finished yet
    if job is None:
        return JobStatusResponse(job_id=job_id, status="queued")

    if job.is_failed:
        return JobStatusResponse(job_id=job_id, status="failed", error=str(job.exc_info))

    if job.is_started:
        return JobStatusResponse(job_id=job_id, status="running")

    return JobStatusResponse(job_id=job_id, status="queued")
