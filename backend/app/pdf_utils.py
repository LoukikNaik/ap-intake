"""PDF helpers.

We render each PDF page to a PNG image and feed those to the agent as vision input.
Why images rather than raw PDF passthrough:
  - Works identically across providers via LiteLLM (gpt-5-mini AND Claude).
  - Naturally handles the scanned/skewed invoice — it's already an image.
This is still native vision (no OCR step); modern models read the rendered pages directly.
"""

import base64
import hashlib

import fitz  # PyMuPDF

# 170 DPI keeps small invoice text legible without exploding image-token cost.
_RENDER_DPI = 170


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def render_pdf_to_data_urls(pdf_bytes: bytes, pages: list[int] | None = None) -> list[str]:
    """Return one base64 PNG data URL per page (optionally only the given 1-based pages)."""
    urls: list[str] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for i, page in enumerate(doc, start=1):
            if pages and i not in pages:
                continue
            pix = page.get_pixmap(dpi=_RENDER_DPI)
            png = pix.tobytes("png")
            b64 = base64.b64encode(png).decode()
            urls.append(f"data:image/png;base64,{b64}")
    return urls


def pdf_to_data_url(pdf_bytes: bytes) -> str:
    """Base64 data URL for a whole PDF — for native file input."""
    return f"data:application/pdf;base64,{base64.b64encode(pdf_bytes).decode()}"


def render_page_png(pdf_bytes: bytes, page: int, rotate: int = 0) -> bytes:
    """Render a single 1-based page to PNG bytes (for the side-by-side review view).

    `rotate` (0/90/180/270) is applied on top of the page's own rotation — lets a reviewer
    straighten a sideways scan.
    """
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        idx = max(1, min(page, doc.page_count)) - 1
        pg = doc[idx]
        if rotate:
            pg.set_rotation((pg.rotation + rotate) % 360)
        return pg.get_pixmap(dpi=_RENDER_DPI).tobytes("png")


def slice_pdf(pdf_bytes: bytes, pages: list[int]) -> bytes:
    """Return a new PDF containing only the given 1-based pages (for per-segment native input)."""
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if not pages:
            return pdf_bytes
        out = fitz.open()
        try:
            for p in pages:
                if 1 <= p <= src.page_count:
                    out.insert_pdf(src, from_page=p - 1, to_page=p - 1)
            return out.tobytes() if out.page_count else pdf_bytes
        finally:
            out.close()
    finally:
        src.close()


def page_count(pdf_bytes: bytes) -> int:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return doc.page_count
