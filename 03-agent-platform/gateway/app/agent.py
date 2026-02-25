import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TypedDict, Callable

import requests

from gateway.app.observability import error_envelope


@dataclass
class ToolSpec:
    server: str
    name: str
    required_scope: str
    description: str

    @property
    def full_name(self) -> str:
        return f"{self.server}.{self.name}"


def _matches(pattern: str, full_name: str) -> bool:
    # Very small glob: exact or prefix wildcard "xxx.*"
    if pattern.endswith(".*"):
        return full_name.startswith(pattern[:-2])
    return pattern == full_name


def load_agent_visibility(role: str, path: str) -> List[str]:
    import yaml

    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    roles = (cfg.get("roles") or {})
    role_cfg = (roles.get(role) or {})
    return list(role_cfg.get("visibility") or [])


def filter_tools_for_role(tools: List[ToolSpec], visibility_patterns: List[str]) -> List[ToolSpec]:
    if not visibility_patterns:
        return []
    out: List[ToolSpec] = []
    for t in tools:
        fn = t.full_name
        if any(_matches(p, fn) for p in visibility_patterns):
            out.append(t)
    return out


class AgentState(TypedDict, total=False):
    user_message: str
    conversation_id: str
    model: str
    correlation_id: str

    # llm runtime
    litellm_base_url: str
    virtual_key: str
    timeout_s: int

    # planning
    visible_tools: List[Dict[str, Any]]
    action: Dict[str, Any]
    tool_result: Dict[str, Any]
    final: Dict[str, Any]
    call_tools_fn: Callable[..., Any]


def _litellm_chat_raw(*, litellm_base_url: str, virtual_key: str, model: str, messages: List[Dict[str, str]], timeout_s: int) -> Dict[str, Any]:
    url = f"{litellm_base_url.rstrip('/')}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {virtual_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "stream": False}
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
    if resp.status_code >= 400:
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}
        raise requests.HTTPError(f"litellm_http_{resp.status_code}", response=resp)
    return resp.json()


def _extract_content(resp_json: Dict[str, Any]) -> str:
    return resp_json["choices"][0]["message"]["content"]


def _plan_action_via_llm(*, litellm_base_url: str, virtual_key: str, model: str, user_message: str, visible_tools: List[Dict[str, Any]], timeout_s: int) -> Dict[str, Any]:
    """Ask the LLM to output a single JSON action.

    Action schema:
      {"type":"tool", "server":"mcp_internal", "tool_name":"internal.query_sqlite", "args":{...}}
      or
      {"type":"final", "answer":"..."}
    """

    sys = (
        "You are a tool-using assistant. "
        "You MUST output a single JSON object and NOTHING ELSE. "
        "Choose at most ONE tool call. "
        "If no tool is needed, return type=final."
    )
    tool_lines = []
    for t in visible_tools:
        tool_lines.append(f"- {t['full_name']}: {t.get('description','')} (required_scope={t.get('required_scope')})")
    tool_block = "\n".join(tool_lines) or "(no tools available)"
    user = (
        f"User message: {user_message}\n\n"
        f"Available tools:\n{tool_block}\n\n"
        "Return JSON now."
    )
    raw = _litellm_chat_raw(
        litellm_base_url=litellm_base_url,
        virtual_key=virtual_key,
        model=model,
        messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
        timeout_s=timeout_s,
    )
    content = _extract_content(raw)
    # --- robust JSON parse (do NOT crash agent/run) ---
    content = (content or "").strip()

    # If empty -> fallback final
    if not content:
        return {"type": "final", "answer": "(planner) empty response from LLM"}

    # Best-effort strip code fences
    if content.startswith("```"):
        content = content.strip("`").strip()
        # drop possible language tag on first line
        if "\n" in content:
            content = content.split("\n", 1)[1].strip()

    # Try parse JSON; fallback to final if invalid
    try:
        return json.loads(content)
    except Exception:
        # if LLM accidentally returned plain text, treat it as final answer
        return {"type": "final", "answer": content[:2000]}


def _final_answer_via_llm(*, litellm_base_url: str, virtual_key: str, model: str, user_message: str, tool_result: Optional[Dict[str, Any]], timeout_s: int) -> str:
    sys = "You are a concise assistant. If tool_result is present, use it."
    user = {
        "user_message": user_message,
        "tool_result": tool_result,
    }
    raw = _litellm_chat_raw(
        litellm_base_url=litellm_base_url,
        virtual_key=virtual_key,
        model=model,
        messages=[{"role": "system", "content": sys}, {"role": "user", "content": json.dumps(user, ensure_ascii=False)}],
        timeout_s=timeout_s,
    )
    return _extract_content(raw)


def build_langgraph_agent():
    """Build a small LangGraph state machine.

    We import langgraph lazily so local tooling doesn't require it.
    """

    from langgraph.graph import StateGraph, END

    g = StateGraph(AgentState)

    def plan(state: AgentState) -> AgentState:
        action = _plan_action_via_llm(
            litellm_base_url=state["litellm_base_url"],
            virtual_key=state["virtual_key"],
            model=state["model"],
            user_message=state["user_message"],
            visible_tools=state.get("visible_tools", []),
            timeout_s=state["timeout_s"],
        )
        state["action"] = action
        return state

    def act(state: AgentState) -> AgentState:
        action = state.get("action") or {}
        if action.get("type") != "tool":
            return state
        # Tool invocation MUST go through Gateway final defense: call_tools_fn injected.
        call_tools_fn = state["call_tools_fn"]
        result = call_tools_fn(
            server=action.get("server"),
            tool_name=action.get("tool_name"),
            args=action.get("args") or {},
        )
        state["tool_result"] = result
        return state

    def respond(state: AgentState) -> AgentState:
        action = state.get("action") or {}
        if action.get("type") == "final" and isinstance(action.get("answer"), str):
            final_text = action["answer"]
        else:
            final_text = _final_answer_via_llm(
                litellm_base_url=state["litellm_base_url"],
                virtual_key=state["virtual_key"],
                model=state["model"],
                user_message=state["user_message"],
                tool_result=state.get("tool_result"),
                timeout_s=state["timeout_s"],
            )
        state["final"] = {"reply": final_text}
        return state

    def route_after_plan(state: AgentState) -> str:
        action = state.get("action") or {}
        return "act" if action.get("type") == "tool" else "respond"

    g.add_node("plan", plan)
    g.add_node("act", act)
    g.add_node("respond", respond)
    g.set_entry_point("plan")
    g.add_conditional_edges("plan", route_after_plan, {"act": "act", "respond": "respond"})
    g.add_edge("act", "respond")
    g.add_edge("respond", END)
    return g.compile()
