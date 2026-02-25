import uuid
from typing import Optional


CORRELATION_HEADER = "x-correlation-id"


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def get_correlation_id_from_headers(headers: dict) -> Optional[str]:
    for k, v in headers.items():
        if k.lower() == CORRELATION_HEADER:
            return v
    return None


def error_envelope(*, code: str, message: str, correlation_id: str, detail: object | None = None) -> dict:
    payload = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "correlation_id": correlation_id,
        },
    }
    if detail is not None:
        payload["error"]["detail"] = detail
    return payload
