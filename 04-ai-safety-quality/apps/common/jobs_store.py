from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class JobRecord:
    job_id: str
    status: str  # queued|running|finished|failed|needs_review
    request_json: dict[str, Any]
    result_json: dict[str, Any] | None
    error: str | None
    created_at: int
    updated_at: int


class JobsStore:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                  job_id TEXT PRIMARY KEY,
                  status TEXT NOT NULL,
                  request_json TEXT NOT NULL,
                  result_json TEXT,
                  error TEXT,
                  created_at INTEGER NOT NULL,
                  updated_at INTEGER NOT NULL
                )
                """
            )

    def create(self, job_id: str, request_json: dict[str, Any]) -> None:
        now = int(time.time())
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO jobs(job_id,status,request_json,created_at,updated_at) VALUES(?,?,?,?,?)",
                (job_id, "queued", json.dumps(request_json, ensure_ascii=False), now, now),
            )

    def set_status(self, job_id: str, status: str, *, result_json: dict[str, Any] | None = None, error: str | None = None) -> None:
        now = int(time.time())
        with self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET status=?, result_json=?, error=?, updated_at=? WHERE job_id=?",
                (
                    status,
                    json.dumps(result_json, ensure_ascii=False) if result_json is not None else None,
                    error,
                    now,
                    job_id,
                ),
            )

    def get(self, job_id: str) -> JobRecord | None:
        with self._conn() as conn:
            r = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if not r:
            return None
        return JobRecord(
            job_id=r["job_id"],
            status=r["status"],
            request_json=json.loads(r["request_json"]),
            result_json=json.loads(r["result_json"]) if r["result_json"] else None,
            error=r["error"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
