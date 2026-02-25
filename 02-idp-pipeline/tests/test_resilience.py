from app.core.resilience import CircuitBreaker, backoff_seconds

def test_circuit_breaker_opens():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout_s=0.1)
    assert cb.allow_request() is True
    cb.on_failure()
    assert cb.state in ("closed", "open")
    cb.on_failure()
    assert cb.state == "open"
    assert cb.allow_request() is False

def test_circuit_breaker_half_open():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout_s=0.0, half_open_successes=1)
    cb.on_failure()
    assert cb.state == "open"
    assert cb.allow_request() is True  # immediately half-open
    cb.on_success()
    assert cb.state == "closed"

def test_backoff_bounds():
    for i in range(1, 10):
        s = backoff_seconds(i, base=0.5, cap=2.0)
        assert 0.0 <= s <= 2.5  # allow small jitter overshoot
