import os, time, hmac, hashlib, base64, json
from dataclasses import dataclass
from fastapi import Header, HTTPException, Request

JWT_SECRET = os.getenv("JWT_SECRET", "dev_secret_change_me")

@dataclass
class UserCtx:
    user_id: str
    role: str
    scopes: list[str]
    correlation_id: str = ""

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

def issue_token(user_id: str, role: str, scopes: list[str], exp_seconds: int = 3600) -> str:
    header = {"alg":"HS256","typ":"JWT"}
    payload = {"sub":user_id,"role":role,"scopes":scopes,"exp":int(time.time())+exp_seconds}
    h = _b64url(json.dumps(header).encode())
    p = _b64url(json.dumps(payload).encode())
    sig = hmac.new(JWT_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url(sig)}"

def verify_token(token: str) -> UserCtx:
    try:
        h, p, s = token.split(".")
        sig = hmac.new(JWT_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url(sig), s):
            raise ValueError("bad_sig")
        payload = json.loads(_b64url_decode(p))
        if payload["exp"] < int(time.time()):
            raise ValueError("expired")
        return UserCtx(user_id=payload["sub"], role=payload["role"], scopes=payload["scopes"])
    except Exception:
        raise HTTPException(status_code=401, detail="invalid_token")

def get_user_ctx(request: Request, authorization: str | None = Header(default=None)) -> UserCtx:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer_token")
    u = verify_token(authorization.split(" ", 1)[1])
    # correlation id is set by middleware; fall back to empty
    try:
        u.correlation_id = getattr(request.state, "correlation_id", "")
    except Exception:
        pass
    return u
