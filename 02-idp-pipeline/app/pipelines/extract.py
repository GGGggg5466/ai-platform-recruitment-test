from __future__ import annotations
from typing import Dict, Any, List, Tuple
import hashlib, base64, io
from app.clients.upstreams import call_chat_completions, extract_content, UpstreamPolicy, call_vlm_chat
from PIL import Image
from app.core.quality import assess_text_quality
from pdf2image import convert_from_bytes

policy = UpstreamPolicy()

def mock_docling_extract(file_bytes: bytes) -> str:
    # Placeholder: treat bytes as "some text"
    return "DOC: " + str(file_bytes[:200])

def mock_ocr_extract(file_bytes: bytes) -> str:
    return "OCR: " + str(file_bytes[:200])

def mock_vlm_extract(file_bytes: bytes) -> str:
    # Simulate better extraction
    return "VLM: " + str(file_bytes[:400])

def choose_route_auto(ocr_text: str, threshold: float = 0.72):
    score, signals, reasons = assess_text_quality(ocr_text)
    if score >= threshold:
        return "ocr", score, signals, reasons
    return "vlm", score, signals, reasons

WS06_BASE = "https://ws-06.huannago.com/v1"
WS06_MODEL = "gemma-3-27b-it"

def vlm_from_text(prompt: str) -> tuple[str, dict, int]:
    text, meta, retries = call_vlm_chat(policy=policy, prompt=prompt, image_data_urls=None)
    return text, meta, retries

def image_bytes_to_data_url(image_bytes: bytes, mime: str = "image/png") -> str:
    # 若傳進來不是png也沒關係，我們統一轉 PNG 比較穩
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"

def vlm_extract_from_image_bytes(image_bytes: bytes) -> tuple[str, dict, int]:
    data_url = image_bytes_to_data_url(image_bytes)
    prompt = "Please OCR this image and return extracted text as Markdown."
    text, meta, retries = call_vlm_chat(policy=policy, prompt=prompt, image_data_urls=[data_url])
    return text, meta, retries

def pdf_bytes_to_page_images(pdf_bytes: bytes, max_pages: int = 8) -> list[Image.Image]:
    imgs = convert_from_bytes(pdf_bytes, dpi=150, fmt="png")
    return imgs[:max_pages]

def vlm_extract_from_pdf_bytes(pdf_bytes: bytes) -> tuple[str, dict, int]:
    pages = pdf_bytes_to_page_images(pdf_bytes)
    urls = []
    for im in pages:
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        urls.append(f"data:image/png;base64,{b64}")

    prompt = (
        "You are an IDP system. Extract the PDF content into Markdown.\n"
        "- Preserve headings and paragraphs.\n"
        "- Preserve tables using Markdown table syntax.\n"
        "- If a page is a chart, describe key values/trends briefly.\n"
        "Return Markdown only."
    )
    text, meta, retries = call_vlm_chat(policy=policy, prompt=prompt, image_data_urls=urls)
    meta = {**meta, "pages": len(urls)}
    return text, meta, retries