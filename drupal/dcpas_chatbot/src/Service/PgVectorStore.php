<?php

namespace Drupal\dcpas_chatbot\Service;

/**
 * pgvector (PostgreSQL) vector store backend.
 *
 * Pushes similarity search into PostgreSQL using the pgvector extension's
 * <=> cosine distance operator. No corpus is loaded into PHP memory —
 * the database engine handles ANN (approximate nearest neighbor) search.
 *
 * Requirements:
 *   - Drupal's default database must be PostgreSQL.
 *   - The pgvector extension must be installed: CREATE EXTENSION vector;
 *   - The dcpas_chatbot_pg_embeddings table must exist (see hook_update_9801).
 *   - The table must be populated by the ingestion migration script:
 *       python3 ingestion/migrate_to_pgvector.py
 *
 * See DEPLOY.md § pgvector Setup for the full setup guide.
 *
 * When to use:
 *   Switch from SQLite to pgvector when max_chunks = 50 000 approaches the
 *   PHP memory ceiling, or when query latency at your corpus size is too high.
 *   At 10K chunks, SQLite and pgvector are comparable. At 100K+, pgvector
 *   wins on latency and reliability.
 */
class PgVectorStore extends AbstractVectorStore {

  /**
   * {@inheritdoc}
   *
   * Executes a single pgvector ANN query. Returns top-K chunks above
   * min_score without loading any embeddings into PHP memory.
   */
  public function findSimilar(array $queryVector, int $topK, float $minScore): array {
    // Build the vector literal for pgvector: '[0.1,0.2,...]'
    // Values are cast to float before embedding in SQL to prevent injection.
    $vecLiteral = '[' . implode(',', array_map('floatval', $queryVector)) . ']';

    // cosine_similarity = 1 - cosine_distance (<=>).
    // We filter on (1 - distance) >= min_score and order ASC by distance.
    // The {table} notation uses Drupal's table prefix handling.
    $sql = "
      SELECT c.chunk_id, c.source_url, c.title, c.text,
             (1 - (e.embedding <=> '{$vecLiteral}'::vector)) AS score
      FROM {dcpas_chatbot_chunks} c
      JOIN {dcpas_chatbot_pg_embeddings} e ON c.chunk_id = e.chunk_id
      WHERE (1 - (e.embedding <=> '{$vecLiteral}'::vector)) >= :min_score
      ORDER BY e.embedding <=> '{$vecLiteral}'::vector ASC
      LIMIT :top_k
    ";

    try {
      $rows = $this->database->query($sql, [
        ':min_score' => $minScore,
        ':top_k'     => $topK,
      ])->fetchAll();
    }
    catch (\Exception $e) {
      $this->logger->error(
        'PgVectorStore::findSimilar failed: @msg. Ensure pgvector is installed and the migration has been run.',
        ['@msg' => $e->getMessage()]
      );
      return [];
    }

    $chunks = [];
    foreach ($rows as $row) {
      // URL scheme guard — same defence-in-depth as SqliteVectorStore.
      $scheme = parse_url($row->source_url, PHP_URL_SCHEME);
      if (!in_array($scheme, ['http', 'https'], TRUE)) {
        continue;
      }
      $chunks[] = [
        'chunk_id'   => $row->chunk_id,
        'source_url' => $row->source_url,
        'title'      => $row->title,
        'text'       => $row->text,
        'score'      => (float) $row->score,
      ];
    }
    return $chunks;
  }

  /**
   * {@inheritdoc}
   *
   * Returns pgvector-specific counts: chunks from the chunks table and
   * vectors from the pg_embeddings table.
   */
  public function getStats(): array {
    try {
      $chunks = (int) $this->database->select('dcpas_chatbot_chunks', 'c')
        ->countQuery()->execute()->fetchField();
      // Count from the pgvector-specific table.
      $embedded = (int) $this->database->select('dcpas_chatbot_pg_embeddings', 'e')
        ->countQuery()->execute()->fetchField();
      return ['chunks' => $chunks, 'embedded' => $embedded];
    }
    catch (\Exception $e) {
      return ['chunks' => 0, 'embedded' => 0];
    }
  }

}
