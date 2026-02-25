from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import Any

app = FastAPI(title="mcp_public")

TOOLS = [
    {"name": "public.echo", "required_scope": "public.echo", "description": "Echo text back"},
    {"name": "public.time", "required_scope": "public.time", "description": "Return server time"},
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
    if req.tool_name == "public.echo":
        out = {"ok": True, "result": req.args.get("text", ""), "correlation_id": cid}
        print(f"CID={cid} tool={req.tool_name} ok=true")
        return out
    if req.tool_name == "public.time":
        import time
        out = {"ok": True, "result": {"epoch": int(time.time())}, "correlation_id": cid}
        print(f"CID={cid} tool={req.tool_name} ok=true")
        return out
    out = {"ok": False, "error": "tool_not_found", "correlation_id": cid}
    print(f"CID={cid} tool={req.tool_name} ok=false code=tool_not_found")
    return out
