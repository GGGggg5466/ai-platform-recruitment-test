import os, time
from redis import Redis

RATE_LIMIT_RPM = int(os.getenv("RATE_LIMIT_RPM", "30"))

def check_rate_limit(r: Redis, user_id: str) -> None:
    key = f"rl:{user_id}:{int(time.time()//60)}"
    n = r.incr(key)
    r.expire(key, 120)
    if n > RATE_LIMIT_RPM:
        from fastapi import HTTPException
        raise HTTPException(status_code=429, detail="rate_limited")
