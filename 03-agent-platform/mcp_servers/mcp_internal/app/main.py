import os
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from typing import Any, Dict, Literal, Optional

from app.sqlite_store import init_db, run_safe_query, SAFE_QUERIES
from app.safe_python import run_task, SAFE_TASKS

app = FastAPI(title="mcp_internal")

SQLITE_PATH = os.getenv("SQLITE_PATH", "/app/data/app.db")

TOOLS = [
    {"name": "internal.read_kb", "required_scope": "internal.read", "description": "Read internal KB snippet"},
    {"name": "internal.query_sqlite", "required_scope": "internal.db", "description": "Run whitelisted SQLite SELECT query (query_id)"},
    {"name": "internal.run_python", "required_scope": "internal.exec", "description": "Run whitelisted python task (task + args)"},
]

class CallReq(BaseModel):
    tool_name: str
    args: Dict[str, Any] = {}


def _cid(request: Request) -> str:
    return request.headers.get("x-correlation-id", "")


def _err(code: str, message: str, correlation_id: str, detail: Any | None = None) -> dict:
    out = {"ok": False, "error": {"code": code, "message": message, "correlation_id": correlation_id}}
    if detail is not None:
        out["error"]["detail"] = detail
    # Backward compatibility: keep `detail` for older clients
    out["detail"] = message
    return out


class QuerySqliteArgs(BaseModel):
    query_id: str
    params: Dict[str, Any] = {}


class RunPythonArgs(BaseModel):
    task: str
    args: Dict[str, Any] = {}

@app.on_event("startup")
def _startup():
    # idempotent init
    init_db(SQLITE_PATH)

@app.get("/tools")
def tools():
    return {"tools": TOOLS}

@app.post("/call")
def call(req: CallReq, request: Request):
    cid = _cid(request)
    if req.tool_name == "internal.read_kb":
        topic = req.args.get("topic", "general")
        out = {"ok": True, "result": f"[INTERNAL_KB] snippet about {topic} ...", "correlation_id": cid}
        print(f"CID={cid} tool={req.tool_name} ok=true")
        return out

    if req.tool_name == "internal.query_sqlite":
        try:
            parsed = QuerySqliteArgs.model_validate(req.args)
        except Exception as e:
            out = _err("validation_error", "invalid_args", cid, detail=str(e))
            print(f"CID={cid} tool={req.tool_name} ok=false code=validation_error")
            return out

        query_id = parsed.query_id
        params = parsed.params or {}
        if query_id not in SAFE_QUERIES:
            out = _err("query_id_not_allowed", "query_id_not_allowed", cid, detail={"allowed": sorted(list(SAFE_QUERIES.keys()))})
            print(f"CID={cid} tool={req.tool_name} ok=false code=query_id_not_allowed")
            return out
        try:
            rows = run_safe_query(query_id, params, sqlite_path=SQLITE_PATH)
        except ValueError as e:
            out = _err("bad_request", str(e), cid)
            print(f"CID={cid} tool={req.tool_name} ok=false code=bad_request")
            return out
        out = {"ok": True, "result": {"query_id": query_id, "rows": rows}, "correlation_id": cid}
        print(f"CID={cid} tool={req.tool_name} ok=true")
        return out

    if req.tool_name == "internal.run_python":
        try:
            parsed = RunPythonArgs.model_validate(req.args)
        except Exception as e:
            out = _err("validation_error", "invalid_args", cid, detail=str(e))
            print(f"CID={cid} tool={req.tool_name} ok=false code=validation_error")
            return out

        task = parsed.task
        args = parsed.args or {}
        if task not in SAFE_TASKS:
            out = _err("task_not_allowed", "task_not_allowed", cid, detail={"allowed": sorted(list(SAFE_TASKS.keys()))})
            print(f"CID={cid} tool={req.tool_name} ok=false code=task_not_allowed")
            return out
        try:
            result = run_task(task, args)
        except Exception as e:
            out = _err("task_error", f"task_error:{type(e).__name__}", cid)
            print(f"CID={cid} tool={req.tool_name} ok=false code=task_error")
            return out
        out = {"ok": True, "result": {"task": task, "output": result}, "correlation_id": cid}
        print(f"CID={cid} tool={req.tool_name} ok=true")
        return out

    out = _err("tool_not_found", "tool_not_found", cid)
    print(f"CID={cid} tool={req.tool_name} ok=false code=tool_not_found")
    return out
