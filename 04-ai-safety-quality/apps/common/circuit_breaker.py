from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class BreakerState:
    failures: int = 0
    open_until_ts: float = 0.0


class CircuitBreaker:
    """Very small in-memory circuit breaker.

    For a course project MVP, this is enough. In production, you would likely
    back this with Redis so all workers share the same breaker state.
    """

    def __init__(self, failure_threshold: int = 3, open_seconds: int = 60):
        self.failure_threshold = failure_threshold
        self.open_seconds = open_seconds
        self._state: dict[str, BreakerState] = {}

    def is_open(self, key: str) -> bool:
        st = self._state.get(key)
        if not st:
            return False
        return time.time() < st.open_until_ts

    def record_success(self, key: str) -> None:
        st = self._state.setdefault(key, BreakerState())
        st.failures = 0
        st.open_until_ts = 0.0

    def record_failure(self, key: str) -> None:
        st = self._state.setdefault(key, BreakerState())
        st.failures += 1
        if st.failures >= self.failure_threshold:
            st.open_until_ts = time.time() + self.open_seconds


breaker = CircuitBreaker()
