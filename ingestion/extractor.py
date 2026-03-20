"""
ingestion/extractor.py — Extract clean plain text from HTML pages.

Strips navigation, scripts, styles, and other non-content elements, leaving
only the main readable text of the page. Also extracts the page title and
a canonical URL for use in chunk metadata.

Usage:
  from ingestion.extractor import extract_html_text
  result = extract_html_text(html_string, source_url)
  # result = {"url": ..., "title": ..., "text": ...}
"""

import re
from html.parser import HTMLParser


# Tags whose entire subtree (including content) should be dropped
_DROP_TAGS = {
    "script", "style", "noscript", "nav", "header", "footer",
    "aside", "form", "button", "input", "select", "textarea",
    "iframe", "svg", "canvas", "figure", "figcaption",
}

# Tags that should produce a line break in the output
_BLOCK_TAGS = {
    "p", "div", "section", "article", "main", "h1", "h2", "h3",
    "h4", "h5", "h6", "li", "dt", "dd", "blockquote", "pre",
    "table", "tr", "td", "th", "br",
}


class _ContentExtractor(HTMLParser):
    """Walk an HTML document and extract clean readable text."""

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.title: str = ""
        self._skip_depth: int = 0     # >0 means we're inside a _DROP_TAG subtree
        self._in_title: bool = False
        self._canonical: str = ""

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        if self._skip_depth > 0:
            self._skip_depth += 1
            return

        if tag in _DROP_TAGS:
            self._skip_depth = 1
            return

        if tag == "title":
            self._in_title = True
            return

        # Capture canonical URL
        if tag == "link":
            attrs_dict = dict(attrs)
            if attrs_dict.get("rel") == "canonical":
                self._canonical = attrs_dict.get("href", "")

        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()

        if self._skip_depth > 0:
            self._skip_depth -= 1
            return

        if tag == "title":
            self._in_title = False

        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        if self._in_title:
            if not self.title:
                self.title = data.strip()
            return
        self.parts.append(data)

    def get_text(self) -> str:
        raw = "".join(self.parts)
        # Collapse runs of whitespace/blank lines
        lines = [line.strip() for line in raw.splitlines()]
        # Remove empty lines and rejoin, preserving paragraph breaks
        cleaned: list[str] = []
        blank_run = 0
        for line in lines:
            if not line:
                blank_run += 1
            else:
                if blank_run > 0:
                    cleaned.append("")  # single blank line between paragraphs
                blank_run = 0
                cleaned.append(line)
        return "\n".join(cleaned).strip()


def extract_html_text(html: str, source_url: str) -> dict:
    """Extract title and clean body text from an HTML string.

    Args:
        html:       raw HTML content
        source_url: the URL this HTML was fetched from (used as fallback title)

    Returns:
        dict with keys: url, title, text
    """
    extractor = _ContentExtractor()
    try:
        extractor.feed(html)
    except Exception:
        pass  # partial parse is still useful

    text = extractor.get_text()
    title = extractor.title or source_url
    url = extractor._canonical or source_url

    return {
        "url": url,
        "title": title,
        "text": text,
    }
