from pydantic import BaseModel
from typing import Any, Optional

class LoginReq(BaseModel):
    user_id: str
    role: str  # intern/employee/admin

class LoginResp(BaseModel):
    token: str

class ToolCallReq(BaseModel):
    server: str
    tool_name: str
    args: dict[str, Any] = {}

class ChatReq(BaseModel):
    conversation_id: str
    message: str
    # Optional: let client choose which model to call via LiteLLM
    # Backward compatible: if omitted and DEFAULT_MODEL not set, use the old demo reply.
    model: Optional[str] = None


class AgentRunReq(BaseModel):
    """LangGraph agent entrypoint (used by Langflow/FE).

    Minimal-invasion design:
    - Runs inside Gateway container.
    - Tool execution goes through existing `/tools/call` (Gateway remains final defense).
    """

    conversation_id: str
    message: str
    model: Optional[str] = None
    max_steps: int = 4
