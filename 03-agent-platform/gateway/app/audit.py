import time, json
from redis import Redis

def audit(r: Redis, event: dict) -> None:
    event["ts"] = int(time.time())
    r.lpush("audit:events", json.dumps(event, ensure_ascii=False))
    r.ltrim("audit:events", 0, 5000)
