"""
ingestion/crawler.py — Web crawler for dcpas.osd.mil.

Crawls HTML pages and downloads PDFs from the target site. Respects robots.txt,
enforces crawl delay, stays on the same domain, and saves raw content to disk for
downstream processing.

Outputs:
  - data/pages/{safe_name}.html   — raw HTML for each crawled page
  - data/pdfs/{safe_name}.pdf     — downloaded PDFs
  - data/crawl_index.json         — manifest of all crawled URLs with metadata

Usage:
  from ingestion.crawler import crawl
  pages, pdfs = crawl(config)
"""

import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser
from pathlib import Path


# Browser-like user agent to avoid bot blocks on public government sites
_USER_AGENT = "Mozilla/5.0 (compatible; DCPASChatbot/1.0; +https://dcpas.osd.mil)"


class _LinkExtractor(HTMLParser):
    """Extract all href links and the page <title> from an HTML document."""

    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.title: str = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href", "")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()


def _safe_filename(url: str) -> str:
    """Convert a URL to a unique safe filesystem name.

    Includes a hash suffix to prevent collisions between URLs that would
    produce the same sanitised path string.
    """
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.strip("/").replace("/", "_") or "index"
    path = re.sub(r"[^\w\-.]", "_", path)
    # Short hash ensures uniqueness even when paths collide
    url_hash = hashlib.sha1(url.encode()).hexdigest()[:8]
    return f"{path[:60]}_{url_hash}"


def _is_pdf(url: str, content_type: str) -> bool:
    """Determine if a URL/response is a PDF."""
    return url.lower().endswith(".pdf") or "application/pdf" in content_type


def _fetch(url: str, timeout: int = 20) -> tuple[bytes, str]:
    """Fetch a URL. Returns (body_bytes, content_type)."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content_type = resp.headers.get("Content-Type", "")
        return resp.read(), content_type


def _load_crawl_index(index_path: Path) -> dict:
    """Load existing crawl index from disk, or return empty dict."""
    if index_path.exists():
        try:
            return json.loads(index_path.read_text())
        except Exception:
            pass
    return {}


def _save_crawl_index(index_path: Path, index: dict) -> None:
    """Persist crawl index to disk."""
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2))


def crawl(config: dict, resume: bool = True) -> tuple[list[str], list[str]]:
    """Crawl the target site and save pages/PDFs to disk.

    Args:
        config: pipeline configuration dict from config.load_config()
        resume:  if True, skip URLs already recorded in crawl_index.json

    Returns:
        (html_paths, pdf_paths) — absolute paths of saved files
    """
    target_url = config["target_url"]
    max_pages = config["max_pages"]
    crawl_delay = config["crawl_delay"]
    pages_dir = Path(config["pages_dir"])
    pdfs_dir = Path(config["pdfs_dir"])

    pages_dir.mkdir(parents=True, exist_ok=True)
    pdfs_dir.mkdir(parents=True, exist_ok=True)

    index_path = pages_dir.parent / "crawl_index.json"
    index = _load_crawl_index(index_path) if resume else {}

    # Parse robots.txt
    parsed_base = urllib.parse.urlparse(target_url)
    base_origin = f"{parsed_base.scheme}://{parsed_base.netloc}"
    robots_url = f"{base_origin}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        print(f"Loaded robots.txt from {robots_url}")
    except Exception as e:
        print(f"Could not load robots.txt: {e} — proceeding without restrictions")

    # Validate that the target URL is HTTPS and on an expected government domain
    if not target_url.startswith("https://"):
        raise ValueError(f"TARGET_URL must use HTTPS. Got: {target_url}")
    if not parsed_base.netloc.endswith(".mil") and not parsed_base.netloc.endswith(".gov"):
        import sys
        print(f"WARNING: target domain '{parsed_base.netloc}' is not a .mil or .gov domain. Proceeding anyway.", file=sys.stderr)

    # BFS crawl
    queue: list[str] = [target_url]
    seen: set[str] = set(index.keys())
    if target_url not in seen:
        seen.add(target_url)

    html_paths: list[str] = [v["path"] for v in index.values() if v.get("type") == "html"]
    pdf_paths: list[str] = [v["path"] for v in index.values() if v.get("type") == "pdf"]

    pages_crawled = len(html_paths) + len(pdf_paths)

    while queue and pages_crawled < max_pages:
        url = queue.pop(0)

        if url in index and resume:
            continue  # already crawled

        if not rp.can_fetch(_USER_AGENT, url):
            print(f"  robots.txt: skip {url}")
            continue

        print(f"  [{pages_crawled + 1}/{max_pages}] {url}")

        try:
            body, content_type = _fetch(url)
        except Exception as e:
            print(f"    error: {e}")
            index[url] = {"type": "error", "error": str(e)}
            _save_crawl_index(index_path, index)
            time.sleep(crawl_delay)
            continue

        if _is_pdf(url, content_type):
            safe = _safe_filename(url)
            dest = pdfs_dir / f"{safe}.pdf"
            dest.write_bytes(body)
            index[url] = {"type": "pdf", "path": str(dest), "size": len(body)}
            pdf_paths.append(str(dest))
            print(f"    saved PDF ({len(body)} bytes)")

        elif "text/html" in content_type or not content_type:
            html_text = body.decode("utf-8", errors="replace")

            # Extract title and links
            extractor = _LinkExtractor()
            try:
                extractor.feed(html_text)
            except Exception:
                pass

            safe = _safe_filename(url)
            dest = pages_dir / f"{safe}.html"
            dest.write_text(html_text, encoding="utf-8")

            index[url] = {
                "type": "html",
                "path": str(dest),
                "title": extractor.title or url,
                "size": len(body),
            }
            html_paths.append(str(dest))

            # Enqueue discovered links on the same domain
            for href in extractor.links:
                abs_url = urllib.parse.urljoin(url, href)
                # Strip fragment and trailing slash for dedup
                abs_url = abs_url.split("#")[0].rstrip("/")
                parsed = urllib.parse.urlparse(abs_url)
                # Stay on same domain, only HTTP(S)
                if parsed.netloc != parsed_base.netloc:
                    continue
                if parsed.scheme not in ("http", "https"):
                    continue
                if abs_url not in seen:
                    seen.add(abs_url)
                    queue.append(abs_url)

        else:
            index[url] = {"type": "skip", "content_type": content_type}

        pages_crawled += 1
        _save_crawl_index(index_path, index)
        time.sleep(crawl_delay)

    print(f"\nCrawl complete: {len(html_paths)} HTML pages, {len(pdf_paths)} PDFs")
    return html_paths, pdf_paths
