from __future__ import annotations

from dataclasses import dataclass

from .injection import InjectionScanResult
from .pii import PiiScanResult


@dataclass
class PolicyDecision:
    action: str  # allow | needs_review | block
    risk_score: float
    confidence: float
    reasons: list[str]


def decide(
    *,
    pii: PiiScanResult,
    inj_user: InjectionScanResult,
    inj_ctx: InjectionScanResult,
    confidence: float,
    risk_block_threshold: float,
    confidence_hitl_threshold: float,
) -> PolicyDecision:
    reasons: list[str] = []
    risk = 0.0

    if pii.found:
        risk = max(risk, 0.6)
        reasons.append("pii_detected:" + ",".join(pii.types))

    if inj_user.found:
        risk = max(risk, inj_user.score)
        reasons.append("prompt_injection_user:" + ",".join(inj_user.hits))

    if inj_ctx.found:
        risk = max(risk, inj_ctx.score)
        reasons.append("prompt_injection_context:" + ",".join(inj_ctx.hits))

    # confidence gates (retrieval quality)
    if confidence < confidence_hitl_threshold:
        reasons.append(f"low_confidence:{confidence:.2f}")

    if risk >= risk_block_threshold:
        return PolicyDecision(action="needs_review", risk_score=risk, confidence=confidence, reasons=reasons)

    if confidence < confidence_hitl_threshold:
        return PolicyDecision(action="needs_review", risk_score=risk, confidence=confidence, reasons=reasons)

    return PolicyDecision(action="allow", risk_score=risk, confidence=confidence, reasons=reasons)
