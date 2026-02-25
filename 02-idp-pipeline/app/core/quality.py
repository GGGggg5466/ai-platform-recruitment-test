import re
from typing import Dict, Tuple, List

def assess_text_quality(text: str) -> Tuple[float, Dict[str, float], List[str]]:
    '''
    Returns: (score 0..1, signals, reason_codes)
    Heuristics are deliberately explainable for reports.
    '''
    if not text:
        return 0.0, {"len": 0.0}, ["EMPTY"]

    total = len(text)
    # ratio of alnum / CJK characters (roughly "readable")
    readable = len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text))
    readable_ratio = readable / max(total, 1)

    # symbol/garbage ratio
    garbage = len(re.findall(r"[^\u4e00-\u9fffA-Za-z0-9\s\.,;:!?()\[\]{}\-_/\\]", text))
    garbage_ratio = garbage / max(total, 1)

    # very short lines indicate fragmented OCR
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    short_lines = sum(1 for ln in lines if len(ln) <= 2)
    short_line_ratio = short_lines / max(len(lines), 1)

    # crude table signal
    table_like = len(re.findall(r"[\|\t]{2,}", text)) + len(re.findall(r"\-{3,}", text))
    table_signal = min(1.0, table_like / 50.0)

    signals = {
        "len": float(total),
        "readable_ratio": float(readable_ratio),
        "garbage_ratio": float(garbage_ratio),
        "short_line_ratio": float(short_line_ratio),
        "table_signal": float(table_signal),
    }

    # score: favor readable, penalize garbage + fragmentation
    score = 0.55*readable_ratio + 0.25*(1.0-garbage_ratio) + 0.20*(1.0-short_line_ratio)
    score = max(0.0, min(1.0, score))

    reasons = []
    if total < 50:
        reasons.append("TOO_SHORT")
    if readable_ratio < 0.55:
        reasons.append("LOW_READABLE_RATIO")
    if garbage_ratio > 0.20:
        reasons.append("HIGH_GARBAGE_RATIO")
    if short_line_ratio > 0.35:
        reasons.append("FRAGMENTED_LINES")
    if table_signal > 0.35:
        reasons.append("TABLE_LIKE_LAYOUT")

    if not reasons:
        reasons.append("OK")

    return score, signals, reasons
