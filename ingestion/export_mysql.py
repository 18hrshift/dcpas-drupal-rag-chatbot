"""
DEPRECATED: ingestion/export_mysql.py

This script is a legacy migration tool from before pgvector was adopted as the
production vector store. It is no longer part of the standard deployment path.

For production migrations, use ingestion/migrate_to_pgvector.py instead.
See PERFORMANCE.md for when and how to migrate to pgvector.

---

ingestion/export_mysql.py — Export the SQLite index to a MySQL-compatible SQL dump.

Reads data/index.sqlite and writes SQL INSERT statements for the three Drupal
module tables. The output file can be imported into the hosted MySQL database
with the standard mysql command-line client.

Usage:
  python3 ingestion/export_mysql.py
  python3 ingestion/export_mysql.py --db data/index.sqlite --out data/export.sql
  python3 ingestion/export_mysql.py --table-prefix drupal_  # if Drupal uses a prefix

Import into MySQL:
  mysql -h host -u user -p dbname < data/export.sql
  # or with prefix:
  mysql -h host -u user -p dbname < data/export.sql
"""

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.config import load_config


def _escape(value: str) -> str:
    """Escape a string value for safe inclusion in a MySQL INSERT statement."""
    if value is None:
        return 'NULL'
    # Escape backslashes, then single quotes
    value = value.replace('\\', '\\\\').replace("'", "\\'")
    return f"'{value}'"


def export(db_path: str, out_path: str, table_prefix: str = '') -> None:
    # Validate table prefix to prevent SQL injection via CLI argument
    if table_prefix and not re.match(r'^[a-zA-Z0-9_]+$', table_prefix):
        raise ValueError(f"Invalid table prefix '{table_prefix}'. Only alphanumeric and underscores allowed.")
    """Read the SQLite index and write a MySQL SQL dump.

    Args:
        db_path:       Path to data/index.sqlite
        out_path:      Output .sql file path
        table_prefix:  Optional Drupal table prefix (e.g. 'drupal_')
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    chunks_table     = f"{table_prefix}dcpas_chatbot_chunks"
    embeddings_table = f"{table_prefix}dcpas_chatbot_embeddings"
    versions_table   = f"{table_prefix}dcpas_chatbot_index_versions"

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    version_str = datetime.now(timezone.utc).strftime('%Y-%m-%d-%H%M')

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(f"-- DCPAS Chatbot corpus export\n")
        f.write(f"-- Generated: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"-- Source: {db_path}\n\n")

        f.write("SET NAMES utf8mb4;\n")
        f.write("SET FOREIGN_KEY_CHECKS = 0;\n\n")

        # --- Chunks ---
        chunks = conn.execute("SELECT * FROM chunks").fetchall()
        if chunks:
            f.write(f"-- Chunks ({len(chunks)} rows)\n")
            f.write(f"TRUNCATE TABLE `{chunks_table}`;\n")
            for row in chunks:
                f.write(
                    f"INSERT INTO `{chunks_table}` "
                    f"(chunk_id, source_url, title, chunk_index, text, char_count, text_hash, created_at) VALUES "
                    f"({_escape(row['chunk_id'])}, {_escape(row['source_url'])}, "
                    f"{_escape(row['title'])}, {row['chunk_index']}, "
                    f"{_escape(row['text'])}, {row['char_count'] or 0}, "
                    f"{_escape(row['text_hash'] or '')}, "
                    f"{_escape(row['created_at'])});\n"
                )
            f.write("\n")

        # --- Embeddings ---
        embeddings = conn.execute("SELECT * FROM embeddings").fetchall()
        if embeddings:
            f.write(f"-- Embeddings ({len(embeddings)} rows)\n")
            f.write(f"TRUNCATE TABLE `{embeddings_table}`;\n")
            for row in embeddings:
                f.write(
                    f"INSERT INTO `{embeddings_table}` "
                    f"(chunk_id, model, dimensions, vector_json, embedded_at) VALUES "
                    f"({_escape(row['chunk_id'])}, {_escape(row['model'])}, "
                    f"{row['dimensions'] or 0}, {_escape(row['vector_json'])}, "
                    f"{_escape(row['embedded_at'])});\n"
                )
            f.write("\n")

        # --- Index version record ---
        f.write(f"-- Index version record\n")
        f.write(
            f"INSERT INTO `{versions_table}` (version, chunk_count, indexed_at, notes) VALUES "
            f"({_escape(version_str)}, {len(chunks)}, "
            f"{_escape(datetime.now(timezone.utc).isoformat())}, "
            f"{_escape('Exported from SQLite ingestion pipeline')});\n\n"
        )

        f.write("SET FOREIGN_KEY_CHECKS = 1;\n")

    conn.close()

    size_kb = out.stat().st_size // 1024
    print(f"Exported {len(chunks)} chunks and {len(embeddings)} embeddings to {out_path} ({size_kb} KB)")
    print(f"\nTo import:")
    print(f"  mysql -h HOST -u USER -p DBNAME < {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Export SQLite corpus to MySQL SQL dump")
    parser.add_argument('--db',           default='', help='Path to index.sqlite (default: data/index.sqlite)')
    parser.add_argument('--out',          default='', help='Output SQL file (default: data/export.sql)')
    parser.add_argument('--table-prefix', default='', help='Drupal table prefix, if any (e.g. drupal_)')
    args = parser.parse_args()

    config = load_config()
    db_path  = args.db  or config['db_path']
    out_path = args.out or str(Path(config['db_path']).parent / 'export.sql')

    if not Path(db_path).exists():
        print(f"Error: database not found at {db_path}")
        print("Run the ingestion pipeline first: python3 ingestion/run_pipeline.py --crawl --embed")
        sys.exit(1)

    export(db_path, out_path, table_prefix=args.table_prefix)


if __name__ == '__main__':
    main()
