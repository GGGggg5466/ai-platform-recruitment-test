from __future__ import annotations
from typing import List, Dict, Any
import re

def simple_chunk(text: str, max_chars: int = 500) -> List[Dict[str, Any]]:
    # very simple: split by blank lines then pack
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks = []
    buf = ""
    idx = 0
    for p in parts:
        if len(buf) + len(p) + 2 <= max_chars:
            buf = (buf + "\n\n" + p).strip()
        else:
            chunks.append({"chunk_id": f"c{idx}", "text": buf})
            idx += 1
            buf = p
    if buf:
        chunks.append({"chunk_id": f"c{idx}", "text": buf})
    return chunks
