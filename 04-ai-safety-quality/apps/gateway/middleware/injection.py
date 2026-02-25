from __future__ import annotations

from dataclasses import dataclass


# Minimal, explainable rules for indirect prompt injection.
# Goal: fast checks (gateway-level) without adding latency.
SUSPICIOUS_PHRASES = [
    "ignore previous",
    "ignore all previous",
    "system prompt",
    "developer message",
    "reveal",
    "exfiltrate",
    "secret",
    "api key",
    "print all",
    "override",
    "jailbreak",
]


@dataclass
class InjectionScanResult:
    found: bool
    hits: list[str]
    score: float


def scan_injection(text: str, *, source: str) -> InjectionScanResult:
    """Return a risk score in [0,1].

    source: 'user' or 'retrieved_context'
    retrieved_context is weighted higher.
    """
    t = (text or "").lower()
    hits = [p for p in SUSPICIOUS_PHRASES if p in t]
    if not hits:
        return InjectionScanResult(False, [], 0.0)

    base = min(1.0, 0.15 * len(hits))
    if source == "retrieved_context":
        base = min(1.0, base + 0.35)  # context injection is more dangerous
    return InjectionScanResult(True, hits, base)
