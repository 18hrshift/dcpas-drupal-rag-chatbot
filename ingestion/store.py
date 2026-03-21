"""
ingestion/store.py — SQLite vector store for the RAG ingestion pipeline.

Stores document chunks, their metadata, and embedding vectors. Used during
ingestion (Python) and can be queried directly or exported for Drupal.

Schema:
  pages  (url, title, crawled_at)
  chunks (chunk_id, source_url, title, chunk_index, text, char_count)
  embeddings (chunk_id, model, dimensions, vector_json, embedded_at)

Usage:
  from ingestion.store import VectorStore
  vs = VectorStore(config["db_path"])
  vs.upsert_chunks(chunks)      # save chunks (without embeddings)
  vs.upsert_embeddings(chunks)  # save embedding vectors
  vs.stats()                    # print counts
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class VectorStore:
    """SQLite-backed store for document chunks and their embeddings."""

    def __init__(self, db_path: str):
        """Open (or create) the SQLite database at db_path."""
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS pages (
                url         TEXT PRIMARY KEY,
                title       TEXT,
                crawled_at  TEXT
            );

            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id    TEXT PRIMARY KEY,
                source_url  TEXT NOT NULL,
                title       TEXT,
                chunk_index INTEGER,
                text        TEXT,
                char_count  INTEGER,
                text_hash   TEXT,
                created_at  TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_chunks_url ON chunks(source_url);

            CREATE TABLE IF NOT EXISTS embeddings (
                chunk_id    TEXT PRIMARY KEY,
                model       TEXT,
                dimensions  INTEGER,
                vector_json TEXT,
                embedded_at TEXT,
                FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id)
            );
        """)
        self._conn.commit()

    def upsert_page(self, url: str, title: str) -> None:
        """Record a crawled page."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO pages (url, title, crawled_at) VALUES (?, ?, ?)",
            (url, title, now),
        )
        self._conn.commit()

    def upsert_chunks(self, chunks: list[dict]) -> None:
        """Insert or replace chunk records (without embedding vectors).

        Computes and stores a SHA-256 hash of each chunk's text at write time.
        Used by verify_hashes() to detect corpus tampering after indexing.
        """
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            (
                c["chunk_id"],
                c["source_url"],
                c.get("title", ""),
                c.get("chunk_index", 0),
                c["text"],
                len(c["text"]),
                hashlib.sha256(c["text"].encode()).hexdigest(),
                now,
            )
            for c in chunks
        ]
        self._conn.executemany(
            """INSERT OR REPLACE INTO chunks
               (chunk_id, source_url, title, chunk_index, text, char_count, text_hash, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        self._conn.commit()

    def upsert_embeddings(self, chunks: list[dict], model: str) -> None:
        """Insert or replace embedding vectors for chunks that have them."""
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for c in chunks:
            vec = c.get("embedding")
            if vec is None:
                continue
            rows.append((
                c["chunk_id"],
                model,
                len(vec),
                json.dumps(vec),
                now,
            ))
        if rows:
            self._conn.executemany(
                """INSERT OR REPLACE INTO embeddings
                   (chunk_id, model, dimensions, vector_json, embedded_at)
                   VALUES (?, ?, ?, ?, ?)""",
                rows,
            )
            self._conn.commit()

    def load_all_embeddings(self) -> list[dict]:
        """Load all chunks that have embeddings.

        Returns list of dicts with: chunk_id, source_url, title, text, embedding (list[float]).
        Used by retrieve.py for similarity search.
        """
        cursor = self._conn.execute("""
            SELECT c.chunk_id, c.source_url, c.title, c.text, e.vector_json
            FROM chunks c
            JOIN embeddings e ON c.chunk_id = e.chunk_id
        """)
        results = []
        for row in cursor:
            results.append({
                "chunk_id": row["chunk_id"],
                "source_url": row["source_url"],
                "title": row["title"],
                "text": row["text"],
                "embedding": json.loads(row["vector_json"]),
            })
        return results

    def chunk_exists(self, chunk_id: str) -> bool:
        """Return True if a chunk record exists."""
        row = self._conn.execute(
            "SELECT 1 FROM chunks WHERE chunk_id = ?", (chunk_id,)
        ).fetchone()
        return row is not None

    def embedding_exists(self, chunk_id: str) -> bool:
        """Return True if an embedding exists for this chunk."""
        row = self._conn.execute(
            "SELECT 1 FROM embeddings WHERE chunk_id = ?", (chunk_id,)
        ).fetchone()
        return row is not None

    def stats(self) -> dict:
        """Return counts of pages, chunks, and embeddings."""
        pages = self._conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        chunks = self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        embedded = self._conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        return {"pages": pages, "chunks": chunks, "embedded": embedded}

    def corpus_hash(self) -> str:
        """Return a stable SHA-256 fingerprint of the full chunk corpus.

        Computed as SHA-256 over all chunk_ids sorted lexicographically and
        joined with newlines. Stable across re-runs as long as the chunk set
        is unchanged. Written to the index manifest after each ingest run.
        """
        cursor = self._conn.execute("SELECT chunk_id FROM chunks ORDER BY chunk_id ASC")
        all_ids = "\n".join(row[0] for row in cursor)
        return hashlib.sha256(all_ids.encode()).hexdigest()

    def verify_hashes(self) -> dict:
        """Re-derive SHA-256 for every chunk text and compare to stored hash.

        Returns:
            {
                "total": int,       # total chunks checked
                "ok": int,          # chunks whose hash matched
                "mismatch": int,    # chunks with hash mismatch (possible tampering)
                "missing_hash": int # chunks that were indexed before text_hash was added
            }
        """
        cursor = self._conn.execute("SELECT chunk_id, text, text_hash FROM chunks")
        total = ok = mismatch = missing = 0
        for row in cursor:
            total += 1
            stored_hash = row[2]
            if not stored_hash:
                missing += 1
                continue
            computed = hashlib.sha256(row[1].encode()).hexdigest()
            if computed == stored_hash:
                ok += 1
            else:
                mismatch += 1
        return {"total": total, "ok": ok, "mismatch": mismatch, "missing_hash": missing}

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
