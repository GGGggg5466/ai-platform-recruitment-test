from __future__ import annotations
import os, json, time
from typing import Dict, Any, List

from app.core.config import DATA_DIR
from app.core.lineage import LineageRecorder
from app.core.quality import assess_text_quality
from app.pipelines.chunking import simple_chunk
from app.stores.qdrant_store import QdrantStore
from app.stores.neo4j_store import Neo4jStore
from app.core.schemas import QualityReport
from app.pipelines.embeddings import embedding_for_chunk
from app.pipelines.extract import (
    mock_docling_extract, mock_ocr_extract, mock_vlm_extract,
    choose_route_auto,
    vlm_from_text, vlm_extract_from_image_bytes, vlm_extract_from_pdf_bytes
)


def upstream_to_str(u):
    """Normalize upstream metadata to a stable string for API/trace.
    Accepts dict (provider/model), string, or None.
    """
    if u is None:
        return None
    if isinstance(u, str):
        return u
    if isinstance(u, dict):
        p = u.get("provider")
        m = u.get("model")
        if p and m:
            return f"{p}:{m}"
        if p:
            return str(p)
        if m:
            return str(m)
    return str(u)

def emit_vlm_done(rec: LineageRecorder, *, kind: str, upstream: Any, retries: int, out_chars: int, pages: int | None = None):
    """
    Unify VLM_EXTRACT_DONE schema:
    - upstream: stable string (provider:model)
    - upstream_meta: dict (full evidence if available)
    """
    upstream_s = upstream_to_str(upstream)
    upstream_meta = upstream if isinstance(upstream, dict) else ({"value": upstream} if upstream is not None else None)

    payload = {
        "kind": kind,
        "upstream": upstream_s,
        "upstream_meta": upstream_meta,
        "retries": retries,
        "out_chars": out_chars,
    }
    if pages is not None:
        payload["pages"] = pages

    # IMPORTANT: do NOT pass meta={...}; pass flattened kwargs
    rec.emit("VLM_EXTRACT_DONE", **payload)

def get_pdf_pages_safe(pdf_bytes: bytes) -> int | None:
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return len(reader.pages)
    except Exception:
        return None
    
def process_job(job_id: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    
    print("WORKER_TASKS_BUILD=2026-02-24_vlm_lineage_fix")
    rec = LineageRecorder(job_id=job_id)
    rec.emit("JOB_STARTED", filename=meta.get("filename"), route_requested=meta.get("route"))

    job_dir = os.path.join(DATA_DIR, "jobs", job_id)
    input_path = meta["input_path"]
    with open(input_path, "rb") as f:
        content = f.read()
        filename = (meta.get("filename") or "").lower()
        is_pdf = filename.endswith(".pdf")
        is_image = filename.endswith((".png", ".jpg", ".jpeg", ".webp"))

    route_requested = meta.get("route", "auto")
    route_trace = []

    # Step 1: base extraction (simulate Docling/OCR)
    rec.emit("BASE_EXTRACT_BEGIN", input_bytes=len(content), is_pdf=is_pdf, is_image=is_image)

    # 只有 auto / ocr 需要 OCR baseline 才做
    ocr_text = None
    if route_requested in ("auto", "ocr"):
        ocr_text = mock_ocr_extract(content)
        rec.emit("OCR_EXTRACT_DONE", ocr_chars=len(ocr_text or ""), input_bytes=len(content))

    chosen_route = None
    quality_report = None

    if route_requested == "ocr":
        chosen_route = "ocr"
        final_text = ocr_text or ""
        score, signals, reasons = assess_text_quality(final_text)
        quality_report = QualityReport(score=score, signals=signals, reason_codes=reasons).model_dump()
        route_trace.append({"stage": "route", "attempted_route": "ocr", "ok": True, "reason": "forced_by_user"})
    elif route_requested == "vlm":

        upstream = None
        retries = 0
        chosen_route = "vlm"
        pages = get_pdf_pages_safe(content)

        if is_pdf:
            rec.emit("VLM_EXTRACT_BEGIN", kind="pdf", pages=pages, input_bytes=len(content))
            try:
                final_text, upstream, retries = vlm_extract_from_pdf_bytes(content)
                emit_vlm_done(rec, kind="pdf", upstream=upstream, retries=retries,
                            out_chars=len(final_text or ""), pages=pages)
                chosen_route = "vlm"
            except Exception as e:
                rec.emit("VLM_EXTRACT_ERROR", kind="pdf", pages=pages, error=str(e))
                route_trace.append({
                    "stage": "vlm",
                    "attempted_route": "vlm",
                    "ok": False,
                    "reason": "upstream_failed_or_timeout",
                })

                # fallback OCR 保底
                rec.emit("OCR_EXTRACT_BEGIN", kind="pdf", pages=pages, reason="vlm_failed_fallback")
                fallback_text = mock_docling_extract(content) or mock_ocr_extract(content)
                final_text = fallback_text or ""
                rec.emit("OCR_EXTRACT_DONE", kind="pdf", pages=pages, ocr_chars=len(final_text), input_bytes=len(content))
                chosen_route = "ocr"

                route_trace.append({
                    "stage": "fallback",
                    "attempted_route": "ocr",
                    "ok": True,
                    "reason": "vlm_failed_fallback",
                })

        elif is_image:
            rec.emit("VLM_EXTRACT_BEGIN", kind="image", input_bytes=len(content))
            try:
                final_text, upstream, retries = vlm_extract_from_image_bytes(content)
                emit_vlm_done(rec, kind="image", upstream=upstream, retries=retries, out_chars=len(final_text or ""))
                chosen_route = "vlm"
            except Exception as e:
                rec.emit("VLM_EXTRACT_ERROR", kind="image", error=str(e))
                route_trace.append({
                    "stage": "vlm",
                    "attempted_route": "vlm",
                    "ok": False,
                    "reason": "upstream_failed_or_timeout",
                })

                rec.emit("OCR_EXTRACT_BEGIN", kind="image", reason="vlm_failed_fallback")
                final_text = (mock_ocr_extract(content) or "")
                rec.emit("OCR_EXTRACT_DONE", kind="image", ocr_chars=len(final_text), input_bytes=len(content))
                chosen_route = "ocr"

                route_trace.append({
                    "stage": "fallback",
                    "attempted_route": "ocr",
                    "ok": True,
                    "reason": "vlm_failed_fallback",
                })
            else:
                rec.emit("VLM_EXTRACT_BEGIN", kind="text")
                final_text, upstream, retries = vlm_from_text("Return OK only.")
                emit_vlm_done(rec, kind="text", upstream=upstream, retries=retries, out_chars=len(final_text or ""))

            score, signals, reasons = assess_text_quality(final_text)
            quality_report = QualityReport(score=score, signals=signals, reason_codes=reasons).model_dump()

            route_trace.append({
                "stage": "route",
                "attempted_route": "vlm",
                "ok": True,
                "reason": "forced_by_user",
                "upstream": upstream_to_str(upstream),
                "retries": retries,
            })
    else:
        # auto: quality gate on OCR -> fallback to VLM
        decision, score, signals, reasons = choose_route_auto(ocr_text or "")
        rec.emit("QUALITY_GATE_DONE", score=score, threshold=0.72, reasons=reasons)

        if decision == "ocr":
            chosen_route = "ocr"
            final_text = ocr_text or ""
        else:
            rec.emit("VLM_EXTRACT_BEGIN", kind="text")
            final_text, upstream, retries = vlm_from_text("Return OK only.")
            emit_vlm_done(rec, kind="text", upstream=upstream, retries=retries, out_chars=len(final_text or ""))
            chosen_route = "vlm"

        score, signals, reasons = assess_text_quality(final_text or "")
        quality_report = QualityReport(score=score, signals=signals, reason_codes=reasons).model_dump()

        # ✅ 統一 route_trace：就算 fallback upstream=None 也不會炸
        route_trace.append({
            "stage": "route",
            "attempted_route": "vlm",
            "ok": (chosen_route == "vlm"),
            "reason": "forced_by_user" if chosen_route == "vlm" else "vlm_failed_fallback",
            "upstream": upstream_to_str(upstream),
            "retries": retries,
        })

    # Step 2: chunking
    rec.emit("CHUNK_BEGIN")
    chunks = simple_chunk(final_text)
    rec.emit("CHUNK_DONE", chunks=len(chunks))

    # Step 3: embeddings + stores
    rec.emit("EMBED_BEGIN")
    vectors = [embedding_for_chunk(c["text"]) for c in chunks]
    rec.emit("EMBED_DONE", vectors=len(vectors), dim=len(vectors[0]) if vectors else 0)

    qdrant = QdrantStore()
    neo4j = Neo4jStore()

    rec.emit("QDRANT_UPSERT_BEGIN")
    qdrant_refs = qdrant.upsert(vectors=vectors, payloads=chunks)
    rec.emit("QDRANT_UPSERT_DONE", points=len(qdrant_refs.get("point_ids", [])))

    rec.emit("NEO4J_WRITE_BEGIN")
    neo_refs = neo4j.write_doc_graph(doc_id=job_id, chunks=chunks)
    rec.emit("NEO4J_WRITE_DONE", chunks=len(chunks))

    # Persist artifacts
    quality_path = os.path.join(job_dir, "quality.json")
    with open(quality_path, "w", encoding="utf-8") as f:
        json.dump(quality_report, f, ensure_ascii=False, indent=2)

    md_path = os.path.join(job_dir, "result.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(final_text)

    # Mark job finished in lineage, then persist lineage once
    rec.emit("JOB_FINISHED")
    lineage_path = rec.persist()

    result = {
        "job_id": job_id,
        "status": "finished",
        "chosen_route": chosen_route,
        "route_trace": route_trace,
        "quality_report": quality_report,
        "stores": {"qdrant": qdrant_refs, "neo4j": neo_refs},
        "artifacts": {
            "result_json_path": os.path.join(job_dir, "result.json"),
            "result_md_path": md_path,
            "lineage_path": lineage_path,
            "quality_path": quality_path,
        },
        "error": None
    }
    with open(os.path.join(job_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result

