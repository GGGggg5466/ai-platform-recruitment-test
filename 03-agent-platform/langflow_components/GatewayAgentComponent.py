# Langflow custom component (示意版)
# 不同 Langflow 版本的 Component API 可能不同，但核心概念相同：
# 在 UI 填入 gateway_url + token；每次 run() 呼叫 /chat 或 /tools/call
import requests

class GatewayAgentComponent:
    display_name = "Gateway Agent"
    description = "Call API Gateway to chat / tool-use with policy enforcement."

    def __init__(self, gateway_url: str, token: str):
        self.gateway_url = gateway_url.rstrip("/")
        self.token = token

    def run(self, conversation_id: str, message: str) -> str:
        r = requests.post(
            f"{self.gateway_url}/chat",
            json={"conversation_id": conversation_id, "message": message},
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["reply"]
