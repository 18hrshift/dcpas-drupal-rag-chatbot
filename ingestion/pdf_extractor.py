"""
ingestion/pdf_extractor.py — Extract plain text from PDF files.

Uses pdftotext (poppler-utils) via subprocess as the primary extraction method,
with a basic fallback that attempts to extract readable ASCII strings from the
PDF binary when pdftotext is unavailable.

Usage:
  from ingestion.pdf_extractor import extract_pdf_text
  text = extract_pdf_text("/path/to/file.pdf")
"""

import re
import subprocess
from pathlib import Path


def extract_pdf_text(pdf_path: str) -> str:
    """Extract plain text from a PDF file.

    Tries pdftotext first (best quality). Falls back to raw string extraction
    from the PDF binary if pdftotext is not installed.

    Args:
        pdf_path: absolute or relative path to the PDF file

    Returns:
        Extracted text as a string. Empty string if extraction fails.
    """
    path = Path(pdf_path)
    if not path.exists():
        return ""

    text = _extract_via_pdftotext(str(path))
    if text.strip():
        return text

    # Fallback: pull readable strings out of the binary
    print(f"  pdftotext failed or returned empty for {path.name}, using fallback")
    return _extract_via_strings(str(path))


def _extract_via_pdftotext(pdf_path: str) -> str:
    """Extract text using pdftotext (poppler-utils). Returns empty string on failure."""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.decode("utf-8", errors="replace")
    except FileNotFoundError:
        pass  # pdftotext not installed
    except subprocess.TimeoutExpired:
        print(f"  pdftotext timed out on {pdf_path}")
    except Exception as e:
        print(f"  pdftotext error: {e}")
    return ""


def _extract_via_strings(pdf_path: str) -> str:
    """Fallback: extract readable ASCII strings from PDF binary.

    This is a last resort. It produces noisy output but captures most
    readable text from simple PDFs. Complex or heavily formatted PDFs
    may yield poor results.
    """
    try:
        with open(pdf_path, "rb") as f:
            raw = f.read()
    except Exception:
        return ""

    # Extract sequences of printable ASCII characters (length >= 4)
    chunks = re.findall(rb"[ -~]{4,}", raw)
    lines = [chunk.decode("ascii", errors="replace") for chunk in chunks]

    # Filter out obvious PDF internals (binary-looking tokens, short noise)
    clean = []
    for line in lines:
        stripped = line.strip()
        # Skip lines that look like PDF object references or pure symbols
        if re.match(r"^[\d\s.]+$", stripped):
            continue
        if len(stripped) < 4:
            continue
        clean.append(stripped)

    return "\n".join(clean)
