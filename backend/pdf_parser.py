"""
pdf_parser.py
-------------
Extracts raw text from PDF resumes using PyPDF2.
Falls back to pdfminer.six for scanned or complex PDFs.

Usage:
    from backend.pdf_parser import extract_text_from_pdf
    text = extract_text_from_pdf("path/to/resume.pdf")
    # or from bytes
    text = extract_text_from_pdf_bytes(pdf_bytes)
"""

import io
import logging
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)


# ============================================================
# PRIMARY PARSER — PyPDF2
# ============================================================

def _extract_with_pypdf2(source: Union[str, Path, bytes, io.BytesIO]) -> str:
    """
    Attempt text extraction using PyPDF2.
    Returns extracted text, or raises on failure.
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
    """
    Fallback extraction using pdfminer.six.
    More accurate for complex layouts and scanned PDFs.
    """
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
    """
    Extract all text from a PDF file on disk.

    Parameters
    ----------
    file_path : str | Path
        Absolute or relative path to the .pdf file.

    Returns
    -------
    str
        Extracted raw text. Empty string if nothing could be extracted.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    # Try PyPDF2 first
    text = ""
    try:
        text = _extract_with_pypdf2(path)
        logger.info("PyPDF2 extracted %d chars from '%s'", len(text), path.name)
    except Exception as exc:
        logger.warning("PyPDF2 failed (%s) — falling back to pdfminer", exc)

    # Fallback if PyPDF2 returned nothing useful
    if not text.strip():
        try:
            text = _extract_with_pdfminer(path)
            logger.info("pdfminer extracted %d chars from '%s'", len(text), path.name)
        except Exception as exc:
            logger.error("pdfminer also failed: %s", exc)

    return text.strip()


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """
    Extract all text from PDF content provided as raw bytes.
    Useful for in-memory uploads (e.g., FastAPI UploadFile).

    Parameters
    ----------
    pdf_bytes : bytes
        Raw PDF binary content.

    Returns
    -------
    str
        Extracted raw text.
    """
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


# ── CLI quick-test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "sample_resume.pdf"
    result = extract_text_from_pdf(pdf_path)
    print(f"\n{'='*60}")
    print(f"Extracted {len(result)} characters")
    print(f"{'='*60}")
    print(result[:2000])
