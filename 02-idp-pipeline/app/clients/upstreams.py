from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple, List, Union
import httpx, time
from app.core.resilience import CircuitBreaker, backoff_seconds
from app.core.config import UPSTREAM_TIMEOUT_S
from pydantic import BaseModel

RETRYABLE = {429, 500, 502, 503, 504}

@dataclass
class Upstream:
    name: str
    base_url: str
    model: str
    breaker: CircuitBreaker

class RouteTraceItem(BaseModel):
    stage: str
    attempted_route: str
    ok: bool
    reason: str | None = None
    upstream: Union[str, dict[str, Any], None] = None
    retries: int = 0

class UpstreamPolicy:
    '''
    Configure your senior's endpoints here.
    Example:
      VLM: ws-05 -> ws-06
      EMBED: ws-04
      LLM: ws-02
    '''
    def __init__(self):
        self.vlm = [
            Upstream("ws-05-qwen3-vl-8b", "https://ws-05.huannago.com/v1", "Qwen3-VL-8B-Instruct-BF16.gguf", CircuitBreaker()),
            Upstream("ws-06-gemma-3-27b", "https://ws-06.huannago.com/v1", "gemma-3-27b-it", CircuitBreaker()),
        ]
        self.embed = [
            Upstream("ws-04-embed", "https://ws-04.wade0426.me", model="Qwen3-Embedding-8B", breaker=CircuitBreaker()),
        ]

async def _post_json(client: httpx.AsyncClient, url: str, payload: Dict[str, Any], timeout_s: float):
    return await client.post(url, json=payload, timeout=timeout_s)

async def call_with_fallback(
    upstreams: List[Upstream],
    path: str,
    payload: Dict[str, Any],
    max_retries: int = 2,
) -> Tuple[Dict[str, Any], str, int]:
    '''
    Returns: (response_json, upstream_name, retries_used)
    Implements: circuit breaker + retry/backoff + fallback.
    '''
    async with httpx.AsyncClient() as client:
        last_err = None
        for up in upstreams:
            if not up.breaker.allow_request():
                continue
            url = up.base_url.rstrip("/") + "/" + path.lstrip("/")
            retries = 0
            for attempt in range(1, max_retries+2):  # 1..max_retries+1
                try:
                    r = await _post_json(client, url, payload, timeout_s=UPSTREAM_TIMEOUT_S)
                    if r.status_code in (429, 500, 502, 503, 504):
                        raise httpx.HTTPStatusError(f"bad status {r.status_code}", request=r.request, response=r)
                    r.raise_for_status()
                    up.breaker.on_success()
                    return r.json(), up.name, retries
                except Exception as e:
                    last_err = e
                    retries += 1
                    up.breaker.on_failure()
                    if attempt <= max_retries+1:
                        sleep_s = backoff_seconds(attempt)
                        await httpx.AsyncClient().aclose()  # noop-safe; keep simple
                        time.sleep(sleep_s)
                        continue
            # try next upstream
        raise RuntimeError(f"All upstreams failed: {last_err}")

def call_chat_completions(base_url: str, model: str, messages: list[dict], timeout_s: float = 60.0) -> dict:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
    }
    with httpx.Client(timeout=timeout_s) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        return r.json()

def extract_content(resp_json: dict) -> str:
    return resp_json["choices"][0]["message"]["content"]

def call_with_fallback_sync(
    upstreams: List[Upstream],
    path: str,
    payload_builder,          # (up:Upstream) -> payload dict
    max_retries: int = 2,
    timeout_s: float = UPSTREAM_TIMEOUT_S,
) -> Tuple[Dict[str, Any], Upstream, int]:
    """
    Return: (response_json, chosen_upstream, retries_used)
    ws-05 -> ws-06 fallback with circuit breaker + retry/backoff.
    """
    last_err: Exception | None = None

    for up in upstreams:
        if not up.breaker.allow_request():
            continue

        url = up.base_url.rstrip("/") + "/" + path.lstrip("/")
        retries_used = 0

        for attempt in range(1, max_retries + 2):  # total attempts = 1 + max_retries
            try:
                payload = payload_builder(up)
                with httpx.Client(timeout=timeout_s) as client:
                    r = client.post(url, json=payload)

                if r.status_code in RETRYABLE:
                    raise httpx.HTTPStatusError(
                        f"retryable status {r.status_code}",
                        request=r.request,
                        response=r,
                    )
                r.raise_for_status()
                up.breaker.on_success()
                return r.json(), up, retries_used

            except Exception as e:
                last_err = e
                retries_used += 1
                up.breaker.on_failure()

                # backoff only if we still have retry budget
                if attempt <= max_retries + 1:
                    time.sleep(backoff_seconds(attempt))
                    continue

        # next upstream
    raise RuntimeError(f"All upstreams failed: {last_err}")

def call_vlm_chat(
    policy: UpstreamPolicy,
    prompt: str,
    image_data_urls: List[str] | None = None,
    max_retries: int = 2,
) -> Tuple[str, Dict[str, Any], int]:
    """
    Return: (text, upstream_meta, retries_used)
    """
    def build_payload(up: Upstream) -> Dict[str, Any]:
        if image_data_urls:
            content = [{"type": "text", "text": prompt}]
            content += [{"type": "image_url", "image_url": {"url": u}} for u in image_data_urls]
            messages = [{"role": "user", "content": content}]
        else:
            messages = [{"role": "user", "content": prompt}]

        return {
            "model": up.model,
            "messages": messages,
            "temperature": 0,
        }

    resp, up, retries = call_with_fallback_sync(
        upstreams=policy.vlm,
        path="/chat/completions",
        payload_builder=build_payload,
        max_retries=max_retries,
    )

    text = extract_content(resp)
    meta = {"provider": up.name, "base_url": up.base_url, "model": up.model}
    return text, meta, retries