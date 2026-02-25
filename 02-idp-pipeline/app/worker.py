import os
from redis import Redis
from rq import Worker, Queue

from app.core.config import REDIS_URL, RQ_QUEUE

def main():
    redis_conn = Redis.from_url(REDIS_URL)
    q = Queue(RQ_QUEUE, connection=redis_conn)
    worker = Worker([q], connection=redis_conn)
    worker.work(with_scheduler=False)

if __name__ == "__main__":
    main()