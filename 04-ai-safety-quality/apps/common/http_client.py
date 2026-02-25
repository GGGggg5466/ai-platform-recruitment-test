from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx


@dataclass
class HttpResult:
    ok: bool
    status_code: int | None
    json: dict[str, Any] | None
    text: str | None
    latency_ms: int
    error: str | None = None


def _is_retryable(status_code: int | None, err: Exception | None) -> bool:
    if err is not None:
        # timeouts, connection errors
        return True
    if status_code is None:
        return True
    return status_code in (429, 500, 502, 503, 504)


async def post_json_with_retry(
    url: str,
    payload: dict[str, Any],
    timeout_s: float,
    retry_max: int,
    backoff_s: float,
    headers: dict[str, str] | None = None,
) -> HttpResult:
    headers = headers or {"Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        last_err: str | None = None
        for attempt in range(retry_max + 1):
            t0 = time.time()
            status: int | None = None
            try:
                resp = await client.post(url, json=payload, headers=headers)
                status = resp.status_code
                latency_ms = int((time.time() - t0) * 1000)
                if 200 <= status < 300:
                    try:
                        return HttpResult(True, status, resp.json(), None, latency_ms)
                    except Exception:
                        return HttpResult(True, status, None, resp.text, latency_ms)

                # non-2xx
                if not _is_retryable(status, None) or attempt >= retry_max:
                    return HttpResult(False, status, None, resp.text, latency_ms, error=f"HTTP {status}")
                last_err = f"HTTP {status}"

            except Exception as e:
                latency_ms = int((time.time() - t0) * 1000)
                if not _is_retryable(status, e) or attempt >= retry_max:
                    return HttpResult(False, status, None, None, latency_ms, error=str(e))
                last_err = str(e)

            # backoff
            await asyncio.sleep(backoff_s * (2**attempt))

        return HttpResult(False, None, None, None, 0, error=last_err or "unknown")
