"""
ingestion/evaluate.py — Retrieval evaluation against Q&A fixture pairs.

Loads fixtures from tests/eval/fixtures.json, runs each question through the
retrieval pipeline, and reports top-1 / top-3 hit rates and average cosine
similarity. A "hit" is when any expected URL is a prefix of a retrieved chunk's
source_url (exact match not required — a page can have multiple chunks).

Usage:
  python3 ingestion/evaluate.py
  python3 ingestion/evaluate.py --fixtures tests/eval/fixtures.json --top-k 5
  python3 ingestion/evaluate.py --verbose

Exit code 0 always (eval is advisory, not a pass/fail gate unless --strict).
Exit code 1 with --strict if top-1 hit rate < 0.50.

This module is stdlib-only. No third-party packages.
"""

import argparse
import json
import sys
from pathlib import Path

# Allow running from the project root (python3 ingestion/evaluate.py)
_project_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))

from ingestion.config import load_config
from ingestion.retrieve import retrieve


def _url_hit(expected_urls: list[str], retrieved_chunks: list[dict]) -> bool:
    """Return True if any retrieved chunk's source_url starts with any expected URL."""
    for chunk in retrieved_chunks:
        url = chunk.get("source_url", "")
        for expected in expected_urls:
            if url.startswith(expected):
                return True
    return False


def run_eval(fixtures_path: Path, top_k: int, verbose: bool, strict: bool) -> int:
    """Run the evaluation and print a report. Returns exit code."""
    config = load_config()

    if not fixtures_path.exists():
        print(f"ERROR: fixtures file not found: {fixtures_path}", file=sys.stderr)
        return 1

    with open(fixtures_path) as f:
        fixtures = json.load(f)

    if not fixtures:
        print("No fixtures found.", file=sys.stderr)
        return 1

    print(f"Evaluating {len(fixtures)} fixtures  top_k={top_k}  db={config['db_path']}")
    print("-" * 60)

    top1_hits = 0
    top3_hits = 0
    total_scores = []
    results = []

    for fx in fixtures:
        fxid = fx.get("id", "?")
        question = fx["question"]
        expected = fx["expected_urls"]

        chunks = retrieve(question, config, top_k=top_k)

        hit1 = _url_hit(expected, chunks[:1])
        hit3 = _url_hit(expected, chunks[:3])
        avg_score = (sum(c["score"] for c in chunks) / len(chunks)) if chunks else 0.0
        top_score = chunks[0]["score"] if chunks else 0.0

        if hit1:
            top1_hits += 1
        if hit3:
            top3_hits += 1
        total_scores.append(top_score)

        results.append({
            "id": fxid,
            "hit1": hit1,
            "hit3": hit3,
            "top_score": top_score,
            "avg_score": avg_score,
        })

        if verbose:
            h1 = "HIT" if hit1 else "miss"
            h3 = "HIT" if hit3 else "miss"
            print(f"  [{fxid}] top1={h1}  top3={h3}  top_score={top_score:.3f}")
            print(f"    Q: {question}")
            if chunks:
                print(f"    #1: {chunks[0]['source_url']}  ({chunks[0]['score']:.3f})")
            else:
                print("    #1: (no results)")
            print()

    total = len(fixtures)
    top1_rate = top1_hits / total
    top3_rate = top3_hits / total
    mean_top_score = sum(total_scores) / total if total_scores else 0.0

    print("-" * 60)
    print(f"Fixtures evaluated : {total}")
    print(f"Top-1 hit rate     : {top1_hits}/{total}  ({top1_rate:.1%})")
    print(f"Top-3 hit rate     : {top3_hits}/{total}  ({top3_rate:.1%})")
    print(f"Mean top score     : {mean_top_score:.3f}")
    print()

    # Guidance thresholds (from PERFORMANCE.md)
    if top1_rate >= 0.70:
        print("Retrieval quality: GOOD  (top-1 >= 70%)")
    elif top1_rate >= 0.50:
        print("Retrieval quality: ACCEPTABLE  (top-1 >= 50%, < 70% — review low-scoring fixtures)")
    else:
        print("Retrieval quality: POOR  (top-1 < 50% — check corpus coverage and min_score)")

    if strict and top1_rate < 0.50:
        print("--strict: top-1 < 50%, exiting 1")
        return 1

    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate retrieval hit rate against Q&A fixture pairs."
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=_project_root / "tests" / "eval" / "fixtures.json",
        help="Path to fixtures JSON file (default: tests/eval/fixtures.json)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of chunks to retrieve per query (default: 5)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-fixture results",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if top-1 hit rate < 50%%",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(run_eval(args.fixtures, args.top_k, args.verbose, args.strict))
