"""
ingestion/retrieve.py — Cosine similarity retrieval from the local vector store.

Loads all embeddings from SQLite, embeds the query, computes cosine similarity
in Python, and returns the top-K most relevant chunks with source metadata.

This module is the retrieval half used during testing. The same logic is
reimplemented in PHP inside the Drupal module (Sprint 2) for runtime queries.

Usage:
  from ingestion.retrieve import retrieve
  results = retrieve("What is the GS pay scale?", config, top_k=5)
  for r in results:
      print(r["score"], r["title"], r["source_url"])
      print(r["text"][:200])
"""

import math

from ingestion.embedder import embed_query
from ingestion.store import VectorStore


def retrieve(query: str, config: dict, top_k: int = 5) -> list[dict]:
    """Find the top-K most relevant chunks for a query.

    Args:
        query:  the user's question or search text
        config: pipeline config dict from config.load_config()
        top_k:  number of results to return

    Returns:
        List of chunk dicts sorted by descending similarity score, each with:
        chunk_id, source_url, title, text, score (float 0–1).
    """
    vs = VectorStore(config["db_path"])
    corpus = vs.load_all_embeddings()
    vs.close()

    if not corpus:
        print("No embeddings found in store. Run the pipeline first.")
        return []

    query_vec = embed_query(query, config)

    scored = []
    for chunk in corpus:
        score = _cosine_similarity(query_vec, chunk["embedding"])
        scored.append({
            "chunk_id": chunk["chunk_id"],
            "source_url": chunk["source_url"],
            "title": chunk["title"],
            "text": chunk["text"],
            "score": score,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two equal-length vectors.

    Returns a float in [-1, 1]. Returns 0.0 if either vector has zero magnitude.
    """
    if len(a) != len(b):
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))

    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0

    return dot / (mag_a * mag_b)
