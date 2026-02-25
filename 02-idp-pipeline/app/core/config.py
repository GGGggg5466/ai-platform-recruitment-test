import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RQ_QUEUE = os.getenv("RQ_QUEUE", "default")
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
UPSTREAM_TIMEOUT_S = float(os.getenv("UPSTREAM_TIMEOUT_S", "30"))
