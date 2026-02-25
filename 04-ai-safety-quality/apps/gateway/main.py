from __future__ import annotations
from apps.common.http_client import post_json_with_retry

import os
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from redis import Redis
from rq import Queue

from apps.common.config import settings
from apps.common.jobs_store import JobsStore
from apps.common.pipeline import run_pipeline_safe
from apps.gateway.hitl.routes import build_router
from apps.gateway.hitl.store import HitlStore
from apps.gateway.observability.langfuse import LangfuseClient


load_dotenv()

app = FastAPI(title="AI Safety & Quality MVP", version="1.0.0")

redis = Redis.from_url(settings.redis_url)
queue = Queue(settings.queue_name, connection=redis)

jobs_db = JobsStore(db_path=os.path.join(settings.data_dir, "jobs.db"))
hitl_store = HitlStore(db_path=os.path.join(settings.data_dir, "hitl.db"))
lf = LangfuseClient()

app.include_router(build_router(hitl_store))


class JobRequest(BaseModel):
    query: str = Field(..., description="User question")
    top_k: int = Field(3, ge=1, le=10)
    use_retrieval: bool = True
    user_id: str | None = None


class JobCreateResponse(BaseModel):
    job_id: str
    status: str


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/v1/jobs", response_model=JobCreateResponse)
def create_job(req: JobRequest):
    job_id = str(uuid.uuid4())
    payload = req.model_dump()
    payload["job_id"] = job_id

    jobs_db.create(job_id, payload)

    # enqueue worker task
    queue.enqueue("apps.worker.tasks.process_job", payload, job_id=job_id)

    return JobCreateResponse(job_id=job_id, status="queued")


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str):
    rec = jobs_db.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="job_not_found")
    return {
        "job_id": rec.job_id,
        "status": rec.status,
        "request": rec.request_json,
        "result": rec.result_json,
        "error": rec.error,
        "created_at": rec.created_at,
        "updated_at": rec.updated_at,
    }


# Synchronous endpoint for promptfoo / DeepEval / Garak
@app.post("/v1/answer")
async def answer(req: JobRequest):
    job_id = str(uuid.uuid4())
    payload = req.model_dump()
    payload["job_id"] = job_id

    trace = lf.start_trace("sync_answer", metadata={"job_id": job_id, "user_id": req.user_id})

    out = await run_pipeline_safe({
        "job_id": str(uuid.uuid4()),
        "query": req.query,
        "top_k": req.top_k,
        "use_retrieval": req.use_retrieval,
        "user_id": "garak"
    })

    # If policy requires review, store HITL record
    if out.get("status") == "needs_review":
        reason = "|".join(out.get("policy", {}).get("reasons", []) or [out.get("reason", "needs_review")])
        hitl_store.upsert_needs_review(job_id, reason=reason, request_json=payload, draft_response=str(out.get("answer", "")))

    lf.end_trace(trace, output=out)

    return out


@app.post("/v1/garak")
async def garak_endpoint(payload: dict):
    """
    Garak adapter (testing-only):
    - bypass retrieval + injection gating + HITL
    - directly call upstream LLM
    - return {"text": "..."} for garak REST generator
    """
    prompt = str(payload.get("prompt") or payload.get("text") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="missing_prompt")

    # 這些名稱請對齊你 settings 裡的實際欄位
    llm_base = os.getenv("LLM_BASE_URL", "").rstrip("/")
    llm_path = os.getenv("LLM_CHAT_PATH", "").strip()
    if not llm_base or not llm_path:
        return {"text": "[CONFIG_ERROR] LLM_BASE_URL or LLM_CHAT_PATH is not set"}

    url = f"{llm_base}{llm_path}"
    timeout_s = float(os.getenv("LLM_TIMEOUT_S", "30"))
    retry_max = int(os.getenv("UPSTREAM_RETRY_MAX", "2"))     # 沒有就用預設
    backoff_s = float(os.getenv("UPSTREAM_BACKOFF_S", "0.5")) # 沒有就用預設
    model_name = os.getenv("LLM_MODEL")  # 你的 shared endpoint 可能需要

    # payload 格式：這裡要對齊你「學長 shared endpoint」吃什麼
    # 你如果 upstream 是 OpenAI-compatible，通常要 messages
    upstream_payload = {
        "model": model_name,  # 有些 server 必填；若不需要也不會壞
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
    }

    r = await post_json_with_retry(
        url=url,
        payload=upstream_payload,
        timeout_s=timeout_s,
        retry_max=retry_max,
        backoff_s=backoff_s,
    )

    if not r.ok:
        # 不要 500，回一個 garak 可吃的 text，方便你在 report 裡解釋「上游不穩」
        return {"text": f"[UPSTREAM_ERROR] {r.error or ''} status={r.status_code} body={r.text or ''}"}

    # 解析 upstream 回傳（不同上游格式不同，先做 best-effort）
    data = r.json or {}
    text = None

    # OpenAI-like: {"choices":[{"message":{"content":"..."}}]}
    try:
        text = data.get("choices", [{}])[0].get("message", {}).get("content")
    except Exception:
        text = None

    # fallback：若 upstream 直接回 {"text": "..."} / {"answer": "..."}
    if not text:
        text = data.get("text") or data.get("answer") or r.text or ""

    return {"text": str(text)}
