from __future__ import annotations

import glob
import os
import uuid
from dataclasses import dataclass
from typing import Any

from apps.common.clients import UpstreamError, cosine_sim, embed_texts, llm_chat
from apps.common.config import settings
from apps.gateway.middleware.injection import scan_injection
from apps.gateway.middleware.pii import mask_pii
from apps.gateway.middleware.policy import PolicyDecision, decide


@dataclass
class RetrievedDoc:
    doc_id: str
    text: str
    score: float


def load_corpus(data_dir: str) -> list[tuple[str, str]]:
    corpus_dir = os.path.join(data_dir, "corpus")
    files = sorted(glob.glob(os.path.join(corpus_dir, "*.txt")))
    out: list[tuple[str, str]] = []
    for fp in files:
        doc_id = os.path.splitext(os.path.basename(fp))[0]
        with open(fp, "r", encoding="utf-8") as f:
            out.append((doc_id, f.read().strip()))
    return out


async def retrieve(query: str, data_dir: str, top_k: int = 3) -> tuple[list[RetrievedDoc], float]:
    corpus = load_corpus(data_dir)
    # embed query + docs (small corpus; for larger corpora you'd precompute)
    texts = [query] + [t for _, t in corpus]
    embs = await embed_texts(texts)
    q = embs[0]
    docs = embs[1:]

    scored: list[RetrievedDoc] = []
    for (doc_id, text), emb in zip(corpus, docs):
        s = cosine_sim(q, emb)
        scored.append(RetrievedDoc(doc_id=doc_id, text=text, score=s))

    scored.sort(key=lambda d: d.score, reverse=True)
    top = scored[:top_k]
    confidence = float(top[0].score) if top else 0.0
    # normalize confidence from cosine [-1,1] to [0,1]
    confidence = max(0.0, min(1.0, (confidence + 1.0) / 2.0))
    return top, confidence


def build_prompt(query: str, retrieved: list[RetrievedDoc]) -> list[dict[str, str]]:
    ctx_blocks = []
    for d in retrieved:
        ctx_blocks.append(f"[doc_id={d.doc_id} score={d.score:.3f}]\n{d.text}")

    ctx = "\n\n".join(ctx_blocks)
    sys = (
        "You are a helpful assistant for a simulated RAG service. "
        "Answer the user's question using ONLY the provided context. "
        "If the context is insufficient, say you don't know. "
        "Always include citations as a list of doc_id values you used."
    )

    user = (
        f"Question:\n{query}\n\n"
        f"Context:\n{ctx}\n\n"
        "Return JSON with keys: answer, citations (array of doc_id), safety_notes (string)."
    )

    return [
        {"role": "system", "content": sys},
        {"role": "user", "content": user},
    ]


def _safe_json_extract(text: str) -> dict[str, Any]:
    """Best-effort extraction when upstream returns extra text."""
    import json

    text = text.strip()
    # quick path
    try:
        return json.loads(text)
    except Exception:
        pass

    # attempt to locate first {...}
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            pass

    return {"answer": text, "citations": [], "safety_notes": "non_json_output"}


async def run_pipeline(request: dict[str, Any]) -> dict[str, Any]:
    """Core pipeline used by worker and sync /v1/answer."""
    query = request["query"]
    job_id = request.get("job_id") or str(uuid.uuid4())

    # Retrieval
    retrieved = []
    confidence = 1.0  # 不檢索時，讓 confidence 不因空檢索被判低（避免誤觸發 HITL）

    use_retrieval = bool(request.get("use_retrieval", True))
    if use_retrieval:
        retrieved, confidence = await retrieve(
            query,
            settings.data_dir,
            top_k=int(request.get("top_k", 3))
        )

    # Injection scan: user + retrieved context
    inj_user = scan_injection(query, source="user")
    ctx_concat = "\n\n".join([d.text for d in retrieved])
    # inj_user 一樣照舊
    inj_user = scan_injection(query, source="user")

    # inj_ctx 永遠是一樣的型別（避免 .score 爆炸）
    ctx_concat = ""
    if use_retrieval and retrieved:
        ctx_concat = "\n".join([d.text for d in retrieved])
    inj_ctx = scan_injection(ctx_concat, source="retrieved_context")

    # Generate draft (may be skipped if context injection is severe)
    # We still generate only if not obviously malicious; otherwise send to HITL.
    if inj_ctx.score >= settings.risk_block_threshold:
        draft = {
            "answer": "[BLOCKED] Retrieved context appears malicious. Escalated for review.",
            "citations": [d.doc_id for d in retrieved],
            "safety_notes": "blocked_due_to_indirect_prompt_injection",
        }
    else:
        messages = build_prompt(query, retrieved)
        raw = await llm_chat(messages)
        draft = _safe_json_extract(raw)

    draft_answer = str(draft.get("answer", ""))

    # PII mask on output
    pii = mask_pii(draft_answer)
    final_answer = pii.masked_text

    decision: PolicyDecision = decide(
        pii=pii,
        inj_user=inj_user,
        inj_ctx=inj_ctx,
        confidence=confidence,
        risk_block_threshold=settings.risk_block_threshold,
        confidence_hitl_threshold=settings.confidence_hitl_threshold,
    )

    result = {
        "job_id": job_id,
        "status": "finished" if decision.action == "allow" else "needs_review",
        "answer": final_answer,
        "citations": draft.get("citations", []),
        "safety_notes": draft.get("safety_notes", ""),
        "retrieval": {
            "top": [{"doc_id": d.doc_id, "score": d.score} for d in retrieved],
            "confidence": confidence,
        },
        "policy": {
            "action": decision.action,
            "risk_score": decision.risk_score,
            "reasons": decision.reasons,
            "pii_found": pii.found,
            "pii_types": pii.types,
            "inj_user_hits": inj_user.hits,
            "inj_ctx_hits": inj_ctx.hits,
        },
    }

    return result


async def run_pipeline_safe(request: dict[str, Any]) -> dict[str, Any]:
    """Same as run_pipeline but converts upstream failures into needs_review."""
    try:
        return await run_pipeline(request)
    except UpstreamError as e:
        return {
            "job_id": request.get("job_id") or str(uuid.uuid4()),
            "status": "needs_review",
            "reason": "upstream_unavailable",
            "detail": str(e),
        }
    except Exception as e:
        return {
            "job_id": request.get("job_id") or str(uuid.uuid4()),
            "status": "failed",
            "error": str(e),
        }
