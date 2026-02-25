from __future__ import annotations

import re
from dataclasses import dataclass


EMAIL_RE = re.compile(r"[\w\.-]+@[\w\.-]+\.[A-Za-z]{2,}")
# Taiwan mobile: 09xxxxxxxx ; simple
TW_MOBILE_RE = re.compile(r"\b09\d{8}\b")
# Taiwan ID: 1 letter + 9 digits (2nd digit 1/2). simplified.
TW_ID_RE = re.compile(r"\b[A-Z][12]\d{8}\b")
# Credit card (very loose)
CC_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")


@dataclass
class PiiScanResult:
    found: bool
    types: list[str]
    masked_text: str


def mask_pii(text: str) -> PiiScanResult:
    types: list[str] = []
    masked = text

    if EMAIL_RE.search(masked):
        types.append("email")
        masked = EMAIL_RE.sub("[EMAIL_REDACTED]", masked)

    if TW_MOBILE_RE.search(masked):
        types.append("phone")
        masked = TW_MOBILE_RE.sub("[PHONE_REDACTED]", masked)

    if TW_ID_RE.search(masked):
        types.append("tw_id")
        masked = TW_ID_RE.sub("[ID_REDACTED]", masked)

    # run CC last to avoid masking IDs / phones twice
    if CC_RE.search(masked):
        types.append("credit_card")
        masked = CC_RE.sub("[CARD_REDACTED]", masked)

    return PiiScanResult(found=bool(types), types=types, masked_text=masked)
