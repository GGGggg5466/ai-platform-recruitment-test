import os
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.core.jobs import enqueue_job, get_job_result
from app.core.schemas import JobSubmitResponse, JobStatusResponse

router = APIRouter()

@router.post("/jobs", response_model=JobSubmitResponse)
async def submit_job(
    file: UploadFile = File(...),
    route: str = Form("auto"),
):
    if route not in ("auto", "ocr", "vlm"):
        raise HTTPException(400, "route must be auto|ocr|vlm")
    content = await file.read()
    job_id = enqueue_job(filename=file.filename, content=content, route=route)
    return JobSubmitResponse(job_id=job_id)

@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str):
    return get_job_result(job_id)
