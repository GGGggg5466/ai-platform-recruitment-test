from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import Any

app = FastAPI(title="mcp_admin")

TOOLS = [
    {"name": "admin.rotate_key", "required_scope": "admin.rotate_key", "description": "Rotate an API key (demo)"},
]

class CallReq(BaseModel):
    tool_name: str
    args: dict[str, Any] = {}

@app.get("/tools")
def tools():
    return {"tools": TOOLS}

@app.post("/call")
def call(req: CallReq, request: Request):
    cid = request.headers.get("x-correlation-id", "")
    if req.tool_name == "admin.rotate_key":
        target = req.args.get("target", "unknown")
        out = {"ok": True, "result": f"rotated key for {target} (demo)", "correlation_id": cid}
        print(f"CID={cid} tool={req.tool_name} ok=true")
        return out
    out = {"ok": False, "error": "tool_not_found", "correlation_id": cid}
    print(f"CID={cid} tool={req.tool_name} ok=false code=tool_not_found")
    return out
