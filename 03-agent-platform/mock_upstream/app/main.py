from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional, Any

app = FastAPI(title="mock_openai_upstream")

class Msg(BaseModel):
    role: str
    content: str

class ChatReq(BaseModel):
    model: str
    messages: List[Msg]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: Optional[bool] = None

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/v1/chat/completions")
def chat(req: ChatReq):
    # Echo the last user message with a stable wrapper.
    last = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
    content = f"(mock_upstream) model={req.model} | echo={last}"
    return {
        "id": "mockcmpl-1",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "model": req.model,
    }
