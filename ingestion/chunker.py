"""
ingestion/chunker.py — Split extracted text into retrieval-sized chunks.

Each chunk is a dict with:
  - chunk_id:    stable identifier (url + index)
  - source_url:  the page this text came from
  - title:       page title
  - text:        the chunk text
  - chunk_index: position within the document (0-based)

Chunk size targets ~400 words with ~50-word overlap to ensure context continuity
across chunk boundaries.

Usage:
  from ingestion.chunker import chunk_document
  chunks = chunk_document(url, title, text)
"""

import hashlib
import re


# Target chunk size in approximate words
CHUNK_SIZE_WORDS = 400

# Overlap between adjacent chunks in approximate words
OVERLAP_WORDS = 50


def chunk_document(url: str, title: str, text: str) -> list[dict]:
    """Split a document's text into overlapping chunks.

    Args:
        url:   source URL (used to build chunk_id and for metadata)
        title: page or document title
        text:  extracted plain text

    Returns:
        List of chunk dicts, each with chunk_id, source_url, title, text, chunk_index.
    """
    if not text.strip():
        return []

    words = _split_words(text)
    if not words:
        return []

    chunks = []
    start = 0
    idx = 0

    while start < len(words):
        end = min(start + CHUNK_SIZE_WORDS, len(words))
        chunk_words = words[start:end]
        chunk_text = " ".join(chunk_words).strip()

        if chunk_text:
            chunk_id = _make_chunk_id(url, idx)
            chunks.append({
                "chunk_id": chunk_id,
                "source_url": url,
                "title": title,
                "text": chunk_text,
                "chunk_index": idx,
            })
            idx += 1

        if end >= len(words):
            break

        # Advance by (chunk_size - overlap) so adjacent chunks share context
        start += max(1, CHUNK_SIZE_WORDS - OVERLAP_WORDS)

    return chunks


def _split_words(text: str) -> list[str]:
    """Split text into words, preserving meaningful whitespace structure."""
    # Replace newlines with spaces but keep the words
    normalized = re.sub(r"\s+", " ", text).strip()
    return normalized.split(" ") if normalized else []


def _make_chunk_id(url: str, index: int) -> str:
    """Generate a stable chunk ID from the source URL and chunk index."""
    raw = f"{url}#{index}"
    digest = hashlib.sha1(raw.encode()).hexdigest()[:12]
    return f"chunk_{digest}"
