"""
pdf_parser.py
-------------
Extracts raw text AND hyperlinks from PDF resumes using PyPDF2.
Falls back to pdfminer.six for scanned or complex PDFs.

Usage:
    from backend.pdf_parser import extract_text_from_pdf, extract_links_from_pdf
    text = extract_text_from_pdf("path/to/resume.pdf")
    links = extract_links_from_pdf_bytes(pdf_bytes)
"""

import io
import logging
import re
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)


# ============================================================
# HYPERLINK EXTRACTION (from PDF annotations)
# ============================================================

def _extract_links_from_pypdf2(source: Union[str, Path, bytes, io.BytesIO]) -> list[str]:
    """
    Extract all hyperlink URLs from PDF annotations using PyPDF2.
    PDF hyperlinks are stored as annotations, NOT in the text stream.
    """
    import PyPDF2

    if isinstance(source, (str, Path)):
        file_obj = open(source, "rb")
        close_after = True
    elif isinstance(source, bytes):
        file_obj = io.BytesIO(source)
        close_after = False
    else:
        file_obj = source
        close_after = False

    links = []
    try:
        reader = PyPDF2.PdfReader(file_obj)
        for page in reader.pages:
            annotations = page.get("/Annots")
            if annotations:
                for annot in annotations:
                    try:
                        annot_obj = annot.get_object()
                        if annot_obj.get("/Subtype") == "/Link":
                            action = annot_obj.get("/A")
                            if action and action.get("/URI"):
                                uri = str(action["/URI"])
                                if uri and uri.startswith(("http://", "https://")):
                                    links.append(uri)
                    except Exception:
                        continue
    finally:
        if close_after:
            file_obj.close()

    return list(dict.fromkeys(links))  # Deduplicate preserving order


def _extract_links_from_text(text: str) -> list[str]:
    """
    Fallback: extract URLs from plain text using regex.
    Catches URLs that might appear as raw text in the PDF body.
    """
    url_pattern = re.compile(
        r'https?://[^\s<>"{}|\\^`\[\]]+',
        re.IGNORECASE,
    )
    found = url_pattern.findall(text)
    # Clean trailing punctuation
    cleaned = []
    for url in found:
        url = url.rstrip(".,;:!?)")
        if url and len(url) > 10:
            cleaned.append(url)
    return list(dict.fromkeys(cleaned))


# ============================================================
# PRIMARY PARSER — PyPDF2
# ============================================================

def _extract_with_pypdf2(source: Union[str, Path, bytes, io.BytesIO]) -> str:
    import PyPDF2

    if isinstance(source, (str, Path)):
        file_obj = open(source, "rb")
        close_after = True
    elif isinstance(source, bytes):
        file_obj = io.BytesIO(source)
        close_after = False
    else:
        file_obj = source
        close_after = False

    try:
        reader = PyPDF2.PdfReader(file_obj)
        pages_text = []
        for page in reader.pages:
            try:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            except Exception as exc:
                logger.warning("PyPDF2: could not extract page — %s", exc)
        return "\n".join(pages_text)
    finally:
        if close_after:
            file_obj.close()


# ============================================================
# FALLBACK PARSER — pdfminer.six
# ============================================================

def _extract_with_pdfminer(source: Union[str, Path, bytes, io.BytesIO]) -> str:
    from pdfminer.high_level import extract_text as pm_extract_text

    if isinstance(source, (str, Path)):
        return pm_extract_text(str(source))
    elif isinstance(source, bytes):
        return pm_extract_text(io.BytesIO(source))
    else:
        return pm_extract_text(source)


# ============================================================
# PUBLIC API
# ============================================================

def extract_text_from_pdf(file_path: Union[str, Path]) -> str:
    """Extract all text from a PDF file on disk."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    text = ""
    try:
        text = _extract_with_pypdf2(path)
        logger.info("PyPDF2 extracted %d chars from '%s'", len(text), path.name)
    except Exception as exc:
        logger.warning("PyPDF2 failed (%s) — falling back to pdfminer", exc)

    if not text.strip():
        try:
            text = _extract_with_pdfminer(path)
            logger.info("pdfminer extracted %d chars from '%s'", len(text), path.name)
        except Exception as exc:
            logger.error("pdfminer also failed: %s", exc)

    return text.strip()


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract all text from PDF content provided as raw bytes."""
    if not pdf_bytes:
        return ""

    text = ""
    try:
        text = _extract_with_pypdf2(pdf_bytes)
        logger.info("PyPDF2 extracted %d chars from in-memory PDF", len(text))
    except Exception as exc:
        logger.warning("PyPDF2 failed on bytes (%s) — falling back to pdfminer", exc)

    if not text.strip():
        try:
            text = _extract_with_pdfminer(pdf_bytes)
            logger.info("pdfminer extracted %d chars from in-memory PDF", len(text))
        except Exception as exc:
            logger.error("pdfminer also failed on bytes: %s", exc)

    return text.strip()


def extract_links_from_pdf_bytes(pdf_bytes: bytes) -> list[str]:
    """
    Extract ALL hyperlinks from a PDF (both annotations and text).
    Returns a deduplicated list of URLs.
    """
    if not pdf_bytes:
        return []

    links = []

    # Method 1: PDF annotations (clickable links)
    try:
        annotation_links = _extract_links_from_pypdf2(pdf_bytes)
        links.extend(annotation_links)
        logger.info("Extracted %d links from PDF annotations", len(annotation_links))
    except Exception as exc:
        logger.warning("Could not extract annotation links: %s", exc)

    # Method 2: Regex from text body (raw URLs in text)
    try:
        text = extract_text_from_pdf_bytes(pdf_bytes)
        text_links = _extract_links_from_text(text)
        links.extend(text_links)
        logger.info("Extracted %d links from PDF text", len(text_links))
    except Exception as exc:
        logger.warning("Could not extract text links: %s", exc)

    # Deduplicate
    return list(dict.fromkeys(links))


def extract_links_from_pdf(file_path: Union[str, Path]) -> list[str]:
    """Extract all hyperlinks from a PDF file on disk."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    with open(path, "rb") as f:
        return extract_links_from_pdf_bytes(f.read())


# ── CLI quick-test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "sample_resume.pdf"

    result = extract_text_from_pdf(pdf_path)
    print(f"\n{'='*60}")
    print(f"Extracted {len(result)} characters")
    print(f"{'='*60}")
    print(result[:2000])

    links = extract_links_from_pdf(pdf_path)
    print(f"\n{'='*60}")
    print(f"Extracted {len(links)} links:")
    for link in links:
        print(f"  → {link}")
