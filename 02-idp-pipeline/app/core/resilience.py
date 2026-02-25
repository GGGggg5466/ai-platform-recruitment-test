import time
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    recovery_timeout_s: float = 30.0
    half_open_successes: int = 1

    state: str = "closed"  # closed|open|half_open
    failures: int = 0
    opened_at: Optional[float] = None
    half_open_ok: int = 0

    def allow_request(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if self.opened_at is None:
                self.opened_at = time.time()
            if time.time() - self.opened_at >= self.recovery_timeout_s:
                self.state = "half_open"
                self.half_open_ok = 0
                return True
            return False
        # half_open
        return True

    def on_success(self):
        if self.state == "half_open":
            self.half_open_ok += 1
            if self.half_open_ok >= self.half_open_successes:
                self.state = "closed"
                self.failures = 0
                self.opened_at = None
        else:
            self.failures = 0

    def on_failure(self):
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.state = "open"
            self.opened_at = time.time()
            self.half_open_ok = 0

def backoff_seconds(attempt: int, base: float = 0.5, cap: float = 8.0, jitter: float = 0.25) -> float:
    # exponential backoff with jitter
    raw = min(cap, base * (2 ** max(0, attempt-1)))
    # jitter in [-jitter, +jitter] proportion
    import random
    factor = 1.0 + random.uniform(-jitter, jitter)
    return max(0.0, raw * factor)
