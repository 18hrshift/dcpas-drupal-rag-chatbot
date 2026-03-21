"""
ingestion/corpus_guard.py — Prompt injection scanner for ingest-time corpus protection.

Scans chunk text for known injection patterns before writing to the index.
Mirrors the pattern set in ChatController::PROMPT_INJECTION_PATTERNS (PHP).

Rationale: poisoned corpus content could inject instructions into the RAG prompt
when retrieved. Skipping at ingest time with a log entry is safer than silently
indexing content that could corrupt the prompt template at query time.

Ownership: ingestion pipeline only. Drupal module does NOT duplicate this logic.
See AGENTS.md for component ownership boundaries.
"""

import re

# Patterns mirror ChatController::PROMPT_INJECTION_PATTERNS.
# Keep these two lists in sync. When updating one, update the other.
_PATTERNS: list[re.Pattern] = [
    # Structural markers that mirror the RAG prompt template
    re.compile(r'\[Source\s+\d+\]', re.IGNORECASE),
    re.compile(r'^---+$', re.MULTILINE),
    re.compile(r'^Question:', re.MULTILINE),
    re.compile(r'^Use the following context', re.MULTILINE),
    # Role / persona hijack phrases
    re.compile(r'^System:', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^Assistant:', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^Override:', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^Final answer:', re.IGNORECASE | re.MULTILINE),
    re.compile(r'<EndOfContext>', re.IGNORECASE),
    re.compile(r'\bdisregard\b', re.IGNORECASE),
    re.compile(r'ignore all\b', re.IGNORECASE),
    re.compile(r'ignore (all )?(previous|prior) instructions?', re.IGNORECASE),
]


def is_poisoned(text: str) -> bool:
    """Return True if text contains any known injection pattern.

    Does NOT raise — callers should handle the False/True result and decide
    whether to skip or flag the chunk. This function is stateless and cheap.
    """
    for pattern in _PATTERNS:
        if pattern.search(text):
            return True
    return False


def first_match(text: str) -> str | None:
    """Return the name of the first matching pattern, or None.

    Useful for log messages so operators know why a chunk was skipped.
    """
    for pattern in _PATTERNS:
        if pattern.search(text):
            return pattern.pattern
    return None
