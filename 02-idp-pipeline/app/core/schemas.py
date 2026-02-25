from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal, Optional

Route = Literal["ocr", "vlm", "hybrid"]
Status = Literal["queued", "running", "finished", "failed"]

class JobSubmitResponse(BaseModel):
    job_id: str

class RouteTraceItem(BaseModel):
    stage: str
    attempted_route: str
    ok: bool
    reason: str
    upstream: Optional[str] = None
    retries: int = 0

class QualityReport(BaseModel):
    score: float = Field(ge=0, le=1)
    reason_codes: List[str] = []
    signals: Dict[str, float] = {}

class StoreRefs(BaseModel):
    qdrant: Dict[str, Any] = {}
    neo4j: Dict[str, Any] = {}

class LineageEvent(BaseModel):
    name: str
    ts: float
    meta: Dict[str, Any] = {}

class Lineage(BaseModel):
    correlation_id: str
    events: List[LineageEvent] = []

class JobArtifacts(BaseModel):
    result_json_path: Optional[str] = None
    result_md_path: Optional[str] = None
    lineage_path: Optional[str] = None
    quality_path: Optional[str] = None

class JobStatusResponse(BaseModel):
    job_id: str
    status: Status
    chosen_route: Optional[Route] = None
    route_trace: List[RouteTraceItem] = []
    quality_report: Optional[QualityReport] = None
    stores: StoreRefs = StoreRefs()
    artifacts: JobArtifacts = JobArtifacts()
    error: Optional[str] = None
