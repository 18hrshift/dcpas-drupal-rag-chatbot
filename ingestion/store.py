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
        """Insert or replace chunk records (without embedding vectors)."""
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            (
                c["chunk_id"],
                c["source_url"],
                c.get("title", ""),
                c.get("chunk_index", 0),
                c["text"],
                len(c["text"]),
                now,
            )
            for c in chunks
        ]
        self._conn.executemany(
            """INSERT OR REPLACE INTO chunks
               (chunk_id, source_url, title, chunk_index, text, char_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
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

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
