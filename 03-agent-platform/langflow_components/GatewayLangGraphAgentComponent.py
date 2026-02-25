# Langflow custom component (Low-code wrapper)
#
# Purpose:
# - Encapsulate "complex" LangGraph agent logic behind a single REST call
# - Langflow only needs: gateway_url (IMPORTANT: use IP, e.g. http://172.20.0.10:8000) + JWT token
#
# Notes:
# - Different Langflow versions have different component APIs. This file stays minimal and
#   acts as a reference implementation.

import requests


class GatewayLangGraphAgentComponent:
    display_name = "Gateway LangGraph Agent"
    description = "Call Gateway /v1/agent/run (LangGraph inside Gateway) with role-based tool visibility."

    def __init__(self, gateway_url: str, token: str, model: str | None = None):
        self.gateway_url = gateway_url.rstrip("/")
        self.token = token
        self.model = model

    def run(self, conversation_id: str, message: str) -> str:
        payload = {"conversation_id": conversation_id, "message": message}
        if self.model:
            payload["model"] = self.model

        r = requests.post(
            f"{self.gateway_url}/v1/agent/run",
            json=payload,
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=60,
        )
        r.raise_for_status()
        return r.json().get("reply", "")
