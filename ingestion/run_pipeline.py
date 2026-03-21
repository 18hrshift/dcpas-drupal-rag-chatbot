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
  python3 ingestion/run_pipeline.py --dry-run --embed    # simulate embed, skip writes
  python3 ingestion/run_pipeline.py --verify             # check corpus hash integrity
  python3 ingestion/run_pipeline.py --crawl --embed --query "test"  # full pipeline + smoke test
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running as a script from any directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.config import load_config
from ingestion.chunker import chunk_document
from ingestion.corpus_guard import is_poisoned, first_match
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


def run_extract_and_embed(config: dict, dry_run: bool = False) -> None:
    """Stages 2–4: Extract text, chunk, and embed all saved pages and PDFs.

    dry_run=True: runs all extract/chunk/scan steps but skips all writes.
    Reports what would be indexed without modifying the store or manifest.
    """
    pages_dir = Path(config["pages_dir"])
    pdfs_dir = Path(config["pdfs_dir"])
    index_path = pages_dir.parent / "crawl_index.json"
    manifest_path = Path(config["db_path"]).parent / "index-manifest.json"

    if dry_run:
        print("\n[DRY RUN] No writes will be made to the store or manifest.\n")

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
    total_skipped_poisoned = 0

    def _process_doc(file_path: Path, text: str, url: str, title: str) -> tuple[int, int]:
        """Chunk one document, scan for injection, save to store.

        Returns (new_chunk_count, skipped_poisoned_count).
        """
        chunks = chunk_document(url, title, text)
        if not chunks:
            return 0, 0

        clean: list[dict] = []
        skipped = 0
        for c in chunks:
            if is_poisoned(c["text"]):
                pattern = first_match(c["text"])
                print(f"  [SKIP-POISONED] {c['chunk_id'][:16]}… matched: {pattern}")
                skipped += 1
            else:
                clean.append(c)

        # Only save chunks not already in store
        new_chunks = [c for c in clean if not vs.chunk_exists(c["chunk_id"])]
        if new_chunks and not dry_run:
            vs.upsert_page(url, title)
            vs.upsert_chunks(new_chunks)
            all_new_chunks.extend(new_chunks)
        elif new_chunks and dry_run:
            all_new_chunks.extend(new_chunks)

        return len(new_chunks), skipped

    # Process HTML pages
    for i, html_file in enumerate(html_files):
        meta = path_to_meta.get(str(html_file), {})
        url = meta.get("url", str(html_file))
        title = meta.get("title", html_file.stem)

        try:
            html = html_file.read_text(encoding="utf-8", errors="replace")
            result = extract_html_text(html, url)
            new_count, skipped = _process_doc(html_file, result["text"], result["url"], result["title"])
            total_skipped_poisoned += skipped
            if new_count:
                label = "[DRY RUN] would add" if dry_run else "new chunks"
                print(f"  [{i+1}/{len(html_files)}] HTML: {new_count} {label} — {title[:60]}")
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
            new_count, skipped = _process_doc(pdf_file, text, url, title)
            total_skipped_poisoned += skipped
            if new_count:
                label = "[DRY RUN] would add" if dry_run else "new chunks"
                print(f"  [{i+1}/{len(pdf_files)}] PDF: {new_count} {label} — {title[:60]}")
        except Exception as e:
            print(f"  [{i+1}/{len(pdf_files)}] PDF error ({pdf_file.name}): {e}")

    print(f"\n{len(all_new_chunks)} new chunks {'(dry run — not written)' if dry_run else 'to embed'}")
    if total_skipped_poisoned:
        print(f"WARNING: {total_skipped_poisoned} chunks skipped (injection pattern matched)")

    if all_new_chunks and not dry_run:
        # Only embed chunks that don't have embeddings yet
        to_embed = [c for c in all_new_chunks if not vs.embedding_exists(c["chunk_id"])]
        print(f"Embedding {len(to_embed)} chunks...")
        if to_embed:
            embed_chunks(to_embed, config)
            vs.upsert_embeddings(to_embed, config["embedding_model"])

    stats = vs.stats()
    print(f"\nStore: {stats['pages']} pages, {stats['chunks']} chunks, {stats['embedded']} embedded")

    # Write index manifest after a successful (non-dry-run) ingest
    if not dry_run:
        _write_manifest(vs, manifest_path, total_skipped_poisoned)

    vs.close()


def _write_manifest(vs: VectorStore, manifest_path: Path, skipped_poisoned: int) -> None:
    """Write index-manifest.json after a completed ingest run.

    Fields: run_at, total_chunks, embedded_chunks, skipped_poisoned, corpus_hash.
    The corpus_hash is a stable SHA-256 fingerprint of the chunk set. Admins
    can compare across runs to detect unexpected corpus changes.
    """
    stats = vs.stats()
    manifest = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "total_chunks": stats["chunks"],
        "embedded_chunks": stats["embedded"],
        "skipped_poisoned": skipped_poisoned,
        "corpus_hash": vs.corpus_hash(),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nManifest written → {manifest_path}")


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


def run_verify(config: dict) -> None:
    """Load the existing index and verify corpus integrity.

    Recomputes SHA-256 for every chunk's text and compares to the stored
    text_hash. Reports mismatches, which may indicate corpus tampering or
    database corruption.

    Also reads and displays the latest index manifest if present.
    """
    print("\n=== Corpus Integrity Verification ===")
    vs = VectorStore(config["db_path"])
    result = vs.verify_hashes()
    vs.close()

    print(f"  Total chunks:    {result['total']}")
    print(f"  Hash OK:         {result['ok']}")
    print(f"  Hash mismatch:   {result['mismatch']}")
    print(f"  No hash stored:  {result['missing_hash']}")

    if result["mismatch"] > 0:
        print("\nWARNING: Hash mismatches detected — corpus may have been tampered with.")
        print("         Re-run the full pipeline to rebuild a clean index.")
    elif result["total"] == 0:
        print("\nNo chunks in index. Run --embed first.")
    else:
        print("\nAll stored hashes verified OK.")

    # Show manifest if available
    manifest_path = Path(config["db_path"]).parent / "index-manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            print(f"\nLatest manifest ({manifest_path}):")
            print(f"  Run at:           {manifest.get('run_at', 'unknown')}")
            print(f"  Total chunks:     {manifest.get('total_chunks', '?')}")
            print(f"  Embedded chunks:  {manifest.get('embedded_chunks', '?')}")
            print(f"  Skipped/poisoned: {manifest.get('skipped_poisoned', '?')}")
            print(f"  Corpus hash:      {manifest.get('corpus_hash', '?')}")
        except Exception as e:
            print(f"\nCould not read manifest: {e}")
    else:
        print(f"\nNo manifest found at {manifest_path}. Run --embed to generate one.")


def main():
    parser = argparse.ArgumentParser(description="DCPAS RAG ingestion pipeline")
    parser.add_argument("--crawl", action="store_true", help="Run the crawler")
    parser.add_argument("--embed", action="store_true", help="Extract, chunk, and embed documents")
    parser.add_argument("--dry-run", action="store_true", help="Simulate --embed: run all steps but skip writes")
    parser.add_argument("--verify", action="store_true", help="Check corpus hash integrity and display manifest")
    parser.add_argument("--query", metavar="TEXT", help="Test retrieval with a query")
    parser.add_argument("--stats", action="store_true", help="Print store statistics")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results for --query")
    args = parser.parse_args()

    if not any([args.crawl, args.embed, args.dry_run, args.verify, args.query, args.stats]):
        parser.print_help()
        sys.exit(0)

    config = load_config()

    if not config["openai_api_key"] and (args.embed or args.query):
        print("Error: OPENAI_API_KEY not set. Copy .env.example to .env and fill in your key.")
        sys.exit(1)

    if args.crawl:
        run_crawl(config)

    if args.embed or args.dry_run:
        run_extract_and_embed(config, dry_run=args.dry_run)

    if args.verify:
        run_verify(config)

    if args.stats:
        run_stats(config)

    if args.query:
        run_query(args.query, config, top_k=args.top_k)


if __name__ == "__main__":
    main()
