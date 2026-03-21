"""
ingestion/migrate_to_pgvector.py — Migrate embeddings from SQLite to pgvector.

Reads the local SQLite index (data/index.sqlite) and writes chunks +
embeddings into a PostgreSQL database with the pgvector extension.

This script:
  1. Creates the dcpas_chatbot_pg_embeddings table if it does not exist.
  2. Reads all chunk + embedding rows from SQLite.
  3. Upserts them into PostgreSQL using psycopg2 + pgvector.
  4. Builds an IVFFlat index on the embedding column for fast ANN search.

Prerequisites:
  pip install psycopg2-binary pgvector
  PostgreSQL: CREATE EXTENSION IF NOT EXISTS vector;

Usage:
  python3 ingestion/migrate_to_pgvector.py
  python3 ingestion/migrate_to_pgvector.py --dry-run   # report row counts, no writes

Environment variables (or .env file):
  PG_DSN — PostgreSQL connection string (required)
    Example: postgresql://drupal:password@localhost:5432/drupal_db
  DB_PATH — Path to SQLite index (default: data/index.sqlite)

The script is idempotent: re-running it upserts rows without duplicating.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))

from ingestion.config import load_config


def _require_deps() -> tuple:
    """Import psycopg2 and pgvector, raising a clear error if missing."""
    try:
        import psycopg2
    except ImportError:
        print(
            "ERROR: psycopg2 is required for pgvector migration.\n"
            "Install it with: pip install psycopg2-binary",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        from pgvector.psycopg2 import register_vector
    except ImportError:
        print(
            "ERROR: pgvector Python client is required.\n"
            "Install it with: pip install pgvector",
            file=sys.stderr,
        )
        sys.exit(1)
    return psycopg2, register_vector


def migrate(db_path: str, pg_dsn: str, dry_run: bool) -> None:
    """Read SQLite embeddings and upsert into pgvector."""
    import os
    pg_dsn = pg_dsn or os.environ.get("PG_DSN", "")
    if not pg_dsn:
        print("ERROR: PG_DSN environment variable is required.", file=sys.stderr)
        sys.exit(1)

    psycopg2, register_vector = _require_deps()

    # --- Read from SQLite ---
    if not Path(db_path).exists():
        print(f"ERROR: SQLite index not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading from SQLite: {db_path}")
    conn_sqlite = sqlite3.connect(db_path)
    conn_sqlite.row_factory = sqlite3.Row
    cur_sqlite = conn_sqlite.cursor()

    cur_sqlite.execute("""
        SELECT c.chunk_id, c.source_url, c.title, c.text, c.chunk_index,
               c.char_count, c.text_hash, c.created_at,
               e.model, e.dimensions, e.vector_json, e.embedded_at
        FROM dcpas_chatbot_chunks c
        JOIN dcpas_chatbot_embeddings e ON c.chunk_id = e.chunk_id
    """)
    rows = cur_sqlite.fetchall()
    conn_sqlite.close()

    print(f"Found {len(rows)} chunk+embedding rows in SQLite.")

    if dry_run:
        print("[dry-run] Would upsert these rows into PostgreSQL. No changes made.")
        return

    # --- Write to PostgreSQL ---
    import numpy as np

    print(f"Connecting to PostgreSQL...")
    conn_pg = psycopg2.connect(pg_dsn)
    register_vector(conn_pg)
    cur_pg = conn_pg.cursor()

    # Ensure pgvector extension is loaded.
    cur_pg.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # Create the chunk table (idempotent).
    cur_pg.execute("""
        CREATE TABLE IF NOT EXISTS dcpas_chatbot_chunks (
            chunk_id    VARCHAR(64)  NOT NULL PRIMARY KEY,
            source_url  TEXT         NOT NULL DEFAULT '',
            title       VARCHAR(500) DEFAULT '',
            chunk_index INTEGER      DEFAULT 0,
            text        TEXT         NOT NULL DEFAULT '',
            char_count  INTEGER      DEFAULT 0,
            text_hash   VARCHAR(64)  DEFAULT '',
            created_at  VARCHAR(32)  DEFAULT ''
        )
    """)

    # Determine vector dimension from first row.
    first_vec = json.loads(rows[0]["vector_json"])
    dims = len(first_vec)
    print(f"Embedding dimensions: {dims}")

    # Create the pgvector embeddings table.
    cur_pg.execute(f"""
        CREATE TABLE IF NOT EXISTS dcpas_chatbot_pg_embeddings (
            chunk_id    VARCHAR(64)      NOT NULL PRIMARY KEY,
            model       VARCHAR(100)     DEFAULT '',
            dimensions  INTEGER          DEFAULT 0,
            embedding   vector({dims})   NOT NULL,
            embedded_at VARCHAR(32)      DEFAULT ''
        )
    """)

    # Upsert all rows.
    upserted = 0
    skipped  = 0
    for row in rows:
        vector = json.loads(row["vector_json"])
        if not vector or len(vector) != dims:
            skipped += 1
            continue

        # Upsert chunk.
        cur_pg.execute("""
            INSERT INTO dcpas_chatbot_chunks
                (chunk_id, source_url, title, chunk_index, text, char_count, text_hash, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (chunk_id) DO UPDATE SET
                source_url  = EXCLUDED.source_url,
                title       = EXCLUDED.title,
                chunk_index = EXCLUDED.chunk_index,
                text        = EXCLUDED.text,
                char_count  = EXCLUDED.char_count,
                text_hash   = EXCLUDED.text_hash
        """, (
            row["chunk_id"], row["source_url"], row["title"] or "",
            row["chunk_index"] or 0, row["text"], row["char_count"] or 0,
            row["text_hash"] or "", row["created_at"] or "",
        ))

        # Upsert embedding.
        cur_pg.execute("""
            INSERT INTO dcpas_chatbot_pg_embeddings
                (chunk_id, model, dimensions, embedding, embedded_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (chunk_id) DO UPDATE SET
                embedding   = EXCLUDED.embedding,
                model       = EXCLUDED.model,
                dimensions  = EXCLUDED.dimensions
        """, (
            row["chunk_id"], row["model"] or "", dims,
            np.array(vector, dtype=np.float32),
            row["embedded_at"] or "",
        ))
        upserted += 1

    # Build IVFFlat cosine index. lists = sqrt(row count) is a common heuristic;
    # minimum 10, maximum 1000.
    lists = max(10, min(1000, int(len(rows) ** 0.5)))
    cur_pg.execute(f"""
        CREATE INDEX IF NOT EXISTS dcpas_pg_emb_ivfflat
        ON dcpas_chatbot_pg_embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = {lists})
    """)

    conn_pg.commit()
    cur_pg.close()
    conn_pg.close()

    print(f"Migration complete: {upserted} rows upserted, {skipped} skipped (bad vectors).")
    print(f"IVFFlat index created with {lists} lists.")
    print()
    print("Next steps:")
    print("  1. In Drupal admin: set Vector store backend → pgvector")
    print("  2. drush dcpas:healthcheck")


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Migrate SQLite RAG index to PostgreSQL + pgvector."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report row counts without writing to PostgreSQL.",
    )
    parser.add_argument(
        "--pg-dsn",
        default="",
        help="PostgreSQL connection string. Overrides PG_DSN env var.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    config = load_config()
    migrate(config["db_path"], args.pg_dsn, args.dry_run)
