"""
ingestion/run_pipeline.py — Main entry point for the RAG ingestion pipeline.

Orchestrates: crawl → extract text → chunk → embed → store

Each stage can be run independently. The pipeline is resumable — already-crawled
pages and already-embedded chunks are skipped on re-run.

Usage:
  python3 ingestion/run_pipeline.py --crawl --embed
  python3 ingestion/run_pipeline.py --embed              # embed only (skip crawl)
  python3 ingestion/run_pipeline.py --query "What is the pay scale?"
  python3 ingestion/run_pipeline.py --stats
  python3 ingestion/run_pipeline.py --crawl --embed --query "test"  # full pipeline + smoke test
"""

import argparse
import json
import sys
from pathlib import Path

# Allow running as a script from any directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.config import load_config
from ingestion.chunker import chunk_document
from ingestion.embedder import embed_chunks
from ingestion.extractor import extract_html_text
from ingestion.pdf_extractor import extract_pdf_text
from ingestion.retrieve import retrieve
from ingestion.store import VectorStore


def run_crawl(config: dict) -> tuple[list[str], list[str]]:
    """Stage 1: Crawl dcpas.osd.mil and save pages/PDFs to disk."""
    from ingestion.crawler import crawl
    print(f"\n=== Stage 1: Crawl {config['target_url']} ===")
    html_paths, pdf_paths = crawl(config, resume=True)
    return html_paths, pdf_paths


def run_extract_and_embed(config: dict) -> None:
    """Stages 2–4: Extract text, chunk, and embed all saved pages and PDFs."""
    pages_dir = Path(config["pages_dir"])
    pdfs_dir = Path(config["pdfs_dir"])
    index_path = pages_dir.parent / "crawl_index.json"

    vs = VectorStore(config["db_path"])

    # Load crawl index to get URL→file mappings
    crawl_index = {}
    if index_path.exists():
        try:
            crawl_index = json.loads(index_path.read_text())
        except Exception:
            pass

    # Build reverse map: file path → URL and title
    path_to_meta: dict[str, dict] = {}
    for url, meta in crawl_index.items():
        if meta.get("type") in ("html", "pdf") and meta.get("path"):
            path_to_meta[meta["path"]] = {
                "url": url,
                "title": meta.get("title", url),
                "type": meta["type"],
            }

    # Collect HTML files
    html_files = list(pages_dir.glob("*.html")) if pages_dir.exists() else []
    pdf_files = list(pdfs_dir.glob("*.pdf")) if pdfs_dir.exists() else []
    total_docs = len(html_files) + len(pdf_files)
    print(f"\n=== Stages 2–4: Extract → Chunk → Embed ({total_docs} documents) ===")

    all_new_chunks: list[dict] = []

    def _process_doc(file_path: Path, text: str, url: str, title: str) -> int:
        """Chunk one document, save to store, return new chunk count."""
        chunks = chunk_document(url, title, text)
        if not chunks:
            return 0

        # Only save chunks that aren't already stored
        new_chunks = [c for c in chunks if not vs.chunk_exists(c["chunk_id"])]
        if new_chunks:
            vs.upsert_page(url, title)
            vs.upsert_chunks(new_chunks)
            all_new_chunks.extend(new_chunks)

        return len(new_chunks)

    # Process HTML pages
    for i, html_file in enumerate(html_files):
        meta = path_to_meta.get(str(html_file), {})
        url = meta.get("url", str(html_file))
        title = meta.get("title", html_file.stem)

        try:
            html = html_file.read_text(encoding="utf-8", errors="replace")
            result = extract_html_text(html, url)
            new_count = _process_doc(html_file, result["text"], result["url"], result["title"])
            if new_count:
                print(f"  [{i+1}/{len(html_files)}] HTML: {new_count} new chunks — {title[:60]}")
        except Exception as e:
            print(f"  [{i+1}/{len(html_files)}] HTML error ({html_file.name}): {e}")

    # Process PDFs
    for i, pdf_file in enumerate(pdf_files):
        meta = path_to_meta.get(str(pdf_file), {})
        url = meta.get("url", str(pdf_file))
        title = meta.get("title", pdf_file.stem)

        try:
            text = extract_pdf_text(str(pdf_file))
            if not text.strip():
                print(f"  [{i+1}/{len(pdf_files)}] PDF empty: {pdf_file.name}")
                continue
            new_count = _process_doc(pdf_file, text, url, title)
            if new_count:
                print(f"  [{i+1}/{len(pdf_files)}] PDF: {new_count} new chunks — {title[:60]}")
        except Exception as e:
            print(f"  [{i+1}/{len(pdf_files)}] PDF error ({pdf_file.name}): {e}")

    print(f"\n{len(all_new_chunks)} new chunks to embed")

    if all_new_chunks:
        # Only embed chunks that don't have embeddings yet
        to_embed = [c for c in all_new_chunks if not vs.embedding_exists(c["chunk_id"])]
        print(f"Embedding {len(to_embed)} chunks...")
        if to_embed:
            embed_chunks(to_embed, config)
            vs.upsert_embeddings(to_embed, config["embedding_model"])

    stats = vs.stats()
    print(f"\nStore: {stats['pages']} pages, {stats['chunks']} chunks, {stats['embedded']} embedded")
    vs.close()


def run_query(query: str, config: dict, top_k: int = 5) -> None:
    """Smoke-test retrieval: run a query and print top results."""
    print(f"\n=== Query: {query!r} ===")
    results = retrieve(query, config, top_k=top_k)
    if not results:
        print("No results.")
        return
    for i, r in enumerate(results, 1):
        print(f"\n[{i}] score={r['score']:.4f} — {r['title']}")
        print(f"    {r['source_url']}")
        print(f"    {r['text'][:200]}...")


def run_stats(config: dict) -> None:
    """Print store statistics."""
    vs = VectorStore(config["db_path"])
    stats = vs.stats()
    vs.close()
    print(f"Pages:    {stats['pages']}")
    print(f"Chunks:   {stats['chunks']}")
    print(f"Embedded: {stats['embedded']}")


def main():
    parser = argparse.ArgumentParser(description="DCPAS RAG ingestion pipeline")
    parser.add_argument("--crawl", action="store_true", help="Run the crawler")
    parser.add_argument("--embed", action="store_true", help="Extract, chunk, and embed documents")
    parser.add_argument("--query", metavar="TEXT", help="Test retrieval with a query")
    parser.add_argument("--stats", action="store_true", help="Print store statistics")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results for --query")
    args = parser.parse_args()

    if not any([args.crawl, args.embed, args.query, args.stats]):
        parser.print_help()
        sys.exit(0)

    config = load_config()

    if not config["openai_api_key"] and (args.embed or args.query):
        print("Error: OPENAI_API_KEY not set. Copy .env.example to .env and fill in your key.")
        sys.exit(1)

    if args.crawl:
        run_crawl(config)

    if args.embed:
        run_extract_and_embed(config)

    if args.stats:
        run_stats(config)

    if args.query:
        run_query(args.query, config, top_k=args.top_k)


if __name__ == "__main__":
    main()
