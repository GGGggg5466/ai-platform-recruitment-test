from __future__ import annotations

from dotenv import load_dotenv
from redis import Redis
from rq import Worker, Queue

from apps.common.config import settings


def main():
    load_dotenv()
    redis = Redis.from_url(settings.redis_url)
    q = Queue(settings.queue_name, connection=redis)
    w = Worker([q], connection=redis)
    w.work(with_scheduler=True)


if __name__ == "__main__":
    main()
