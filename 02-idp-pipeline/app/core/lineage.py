import time, uuid, os, json
from dataclasses import dataclass, field
from typing import Dict, Any, List
from app.core.config import DATA_DIR

@dataclass
class LineageRecorder:
    job_id: str
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    events: List[Dict[str, Any]] = field(default_factory=list)

    def emit(self, name: str, **meta):
        self.events.append({"name": name, "ts": time.time(), "meta": meta})

    def persist(self) -> str:
        job_dir = os.path.join(DATA_DIR, "jobs", self.job_id)
        os.makedirs(job_dir, exist_ok=True)
        path = os.path.join(job_dir, "lineage.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"correlation_id": self.correlation_id, "events": self.events}, f, ensure_ascii=False, indent=2)
        return path
