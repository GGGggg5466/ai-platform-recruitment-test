from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class ReviewItem:
    job_id: str
    status: str  # needs_review | approved | rejected
    reason: str
    request_json: dict[str, Any]
    draft_response: str
    created_at: int
    updated_at: int


class HitlStore:
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
                CREATE TABLE IF NOT EXISTS reviews (
                  job_id TEXT PRIMARY KEY,
                  status TEXT NOT NULL,
                  reason TEXT NOT NULL,
                  request_json TEXT NOT NULL,
                  draft_response TEXT NOT NULL,
                  created_at INTEGER NOT NULL,
                  updated_at INTEGER NOT NULL
                )
                """
            )

    def upsert_needs_review(self, job_id: str, reason: str, request_json: dict[str, Any], draft_response: str) -> None:
        now = int(time.time())
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO reviews(job_id,status,reason,request_json,draft_response,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(job_id) DO UPDATE SET
                  status=excluded.status,
                  reason=excluded.reason,
                  request_json=excluded.request_json,
                  draft_response=excluded.draft_response,
                  updated_at=excluded.updated_at
                """,
                (job_id, "needs_review", reason, json.dumps(request_json, ensure_ascii=False), draft_response, now, now),
            )

    def list_needs_review(self, limit: int = 50) -> list[ReviewItem]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM reviews WHERE status='needs_review' ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def get(self, job_id: str) -> ReviewItem | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM reviews WHERE job_id=?", (job_id,)).fetchone()
        return self._row_to_item(row) if row else None

    def set_status(self, job_id: str, status: str) -> None:
        now = int(time.time())
        with self._conn() as conn:
            conn.execute("UPDATE reviews SET status=?, updated_at=? WHERE job_id=?", (status, now, job_id))

    def _row_to_item(self, r: sqlite3.Row) -> ReviewItem:
        return ReviewItem(
            job_id=r["job_id"],
            status=r["status"],
            reason=r["reason"],
            request_json=json.loads(r["request_json"]),
            draft_response=r["draft_response"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
