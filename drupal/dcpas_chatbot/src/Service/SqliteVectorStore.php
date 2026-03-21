<?php

namespace Drupal\dcpas_chatbot\Service;

/**
 * SQLite (in-process cosine similarity) vector store backend.
 *
 * Loads the full corpus of chunks and their JSON-encoded embeddings into PHP
 * memory, computes cosine similarity in PHP, and returns the top-K results.
 *
 * Memory safety: loads in batches of LOAD_BATCH_SIZE. Stops early with a
 * warning log if PHP memory usage approaches MEMORY_CEILING_FRACTION of
 * memory_limit. The configurable max_chunks is the normal operational cap;
 * ABSOLUTE_ROW_CAP is the hard ceiling regardless of config.
 *
 * Migration trigger: if max_chunks = 50 000 approaches the memory ceiling,
 * switch to PgVectorStore. See CLAUDE.md § Memory Safety and § Confidence
 * Scoring & Evaluation.
 */
class SqliteVectorStore extends AbstractVectorStore {

  /** Hard row cap regardless of max_chunks config. */
  const ABSOLUTE_ROW_CAP = 50000;

  /** Batch size for memory-safe loading. */
  const LOAD_BATCH_SIZE = 1000;

  /**
   * Stop loading when memory usage exceeds this fraction of memory_limit.
   * 0.80 = stop at 80 %. Leaves headroom for cosine similarity + Azure call.
   */
  const MEMORY_CEILING_FRACTION = 0.80;

  /**
   * {@inheritdoc}
   *
   * Loads all embeddings in batches, then scores each chunk against the query
   * vector using cosine similarity in PHP.
   */
  public function findSimilar(array $queryVector, int $topK, float $minScore): array {
    $corpus = $this->loadAllWithEmbeddings();
    if (empty($corpus)) {
      return [];
    }

    $scored = [];
    foreach ($corpus as $chunk) {
      $score = $this->cosineSimilarity($queryVector, $chunk['embedding']);
      if ($score < $minScore) {
        continue;
      }
      $scored[] = [
        'chunk_id'   => $chunk['chunk_id'],
        'source_url' => $chunk['source_url'],
        'title'      => $chunk['title'],
        'text'       => $chunk['text'],
        'score'      => $score,
      ];
    }

    usort($scored, fn($a, $b) => $b['score'] <=> $a['score']);
    return array_slice($scored, 0, $topK);
  }

  /**
   * Load all chunks that have embeddings, applying the memory safety guard.
   *
   * Returns an array of associative arrays:
   *   chunk_id, source_url, title, text, embedding (float[])
   *
   * @return array[]
   */
  public function loadAllWithEmbeddings(): array {
    $config    = $this->configFactory->get('dcpas_chatbot.settings');
    $maxChunks = min(
      (int) ($config->get('max_chunks') ?? 10000),
      self::ABSOLUTE_ROW_CAP
    );
    $memLimit = $this->parseMemoryLimit(ini_get('memory_limit'));

    $results = [];
    $offset  = 0;

    while (TRUE) {
      // Memory ceiling guard — stop before exhausting PHP memory.
      if ($memLimit > 0 && memory_get_usage(TRUE) > $memLimit * self::MEMORY_CEILING_FRACTION) {
        $this->logger->warning(
          'SqliteVectorStore: memory ceiling reached at @n chunks loaded (@used / @limit bytes). '
          . 'Retrieval will operate on a partial corpus. '
          . 'Lower max_chunks or migrate to pgvector for larger corpora.',
          [
            '@n'     => count($results),
            '@used'  => memory_get_usage(TRUE),
            '@limit' => $memLimit,
          ]
        );
        break;
      }

      if (count($results) >= $maxChunks) {
        break;
      }

      $batchSize = min(self::LOAD_BATCH_SIZE, $maxChunks - count($results));

      $query = $this->database->select('dcpas_chatbot_chunks', 'c');
      $query->join('dcpas_chatbot_embeddings', 'e', 'c.chunk_id = e.chunk_id');
      $query->fields('c', ['chunk_id', 'source_url', 'title', 'text']);
      $query->fields('e', ['vector_json']);
      $query->range($offset, $batchSize);

      $batchRows = $query->execute()->fetchAll();
      if (empty($batchRows)) {
        break;
      }

      foreach ($batchRows as $row) {
        $vector = json_decode($row->vector_json, TRUE);
        if (!is_array($vector) || empty($vector)) {
          continue;
        }
        // Validate vector elements: must be finite numerics.
        foreach ($vector as $v) {
          if (!is_float($v) && !is_int($v)) {
            continue 2;
          }
          if (is_infinite($v) || is_nan($v)) {
            continue 2;
          }
        }
        // Validate URL scheme to prevent javascript:/data: URIs in citations.
        $scheme = parse_url($row->source_url, PHP_URL_SCHEME);
        if (!in_array($scheme, ['http', 'https'], TRUE)) {
          continue;
        }

        $results[] = [
          'chunk_id'   => $row->chunk_id,
          'source_url' => $row->source_url,
          'title'      => $row->title,
          'text'       => $row->text,
          'embedding'  => array_map('floatval', $vector),
        ];
      }

      $offset += $batchSize;
    }

    return $results;
  }

  /**
   * Compute cosine similarity between two equal-length float vectors.
   *
   * @return float  Value in [-1, 1]. Returns 0.0 for zero-magnitude or
   *                mismatched-length vectors.
   */
  protected function cosineSimilarity(array $a, array $b): float {
    if (count($a) !== count($b) || empty($a)) {
      return 0.0;
    }
    $dot  = 0.0;
    $magA = 0.0;
    $magB = 0.0;
    foreach ($a as $i => $val) {
      $dot  += $val * $b[$i];
      $magA += $val * $val;
      $magB += $b[$i] * $b[$i];
    }
    $denom = sqrt($magA) * sqrt($magB);
    return $denom > 0.0 ? $dot / $denom : 0.0;
  }

}
