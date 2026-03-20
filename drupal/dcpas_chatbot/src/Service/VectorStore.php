<?php

namespace Drupal\dcpas_chatbot\Service;

use Drupal\Core\Database\Connection;

/**
 * Reads chunk and embedding data from the Drupal MySQL database.
 *
 * NOTE — scaling boundary: loadAllWithEmbeddings() loads the full corpus
 * into PHP memory for in-process cosine similarity. This is intentional and
 * acceptable for demo-scale corpora (~1 000–5 000 chunks). A hard cap of
 * 50 000 rows prevents memory exhaustion on oversized corpora.
 *
 * For production FedRAMP deployments exceeding this size, replace with
 * pgvector, Azure Cognitive Search, or a dedicated vector database.
 */
class VectorStore {

  /** Safety cap to prevent memory exhaustion on large corpora. */
  const MAX_CORPUS_ROWS = 50000;

  public function __construct(
    protected readonly Connection $database,
  ) {}

  /**
   * Load all chunks that have embeddings.
   *
   * Returns an array of associative arrays:
   *   chunk_id, source_url, title, text, embedding (float[])
   *
   * @return array[]
   */
  public function loadAllWithEmbeddings(): array {
    $query = $this->database->select('dcpas_chatbot_chunks', 'c');
    $query->join('dcpas_chatbot_embeddings', 'e', 'c.chunk_id = e.chunk_id');
    $query->fields('c', ['chunk_id', 'source_url', 'title', 'text']);
    $query->fields('e', ['vector_json']);
    $query->range(0, self::MAX_CORPUS_ROWS);

    $results = [];
    foreach ($query->execute() as $row) {
      $vector = json_decode($row->vector_json, TRUE);
      // Skip corrupt rows where the vector is missing or non-numeric.
      if (!is_array($vector) || empty($vector)) {
        continue;
      }
      // Validate that all vector elements are numeric to prevent PHP
      // arithmetic errors in cosineSimilarity().
      foreach ($vector as $v) {
        if (!is_float($v) && !is_int($v)) {
          continue 2;
        }
      }

      // Validate source URL scheme to prevent javascript:/data: URIs
      // from appearing in citation links (stored XSS via the corpus).
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
    return $results;
  }

  /**
   * Return the latest index version string, or 'unknown' if none recorded.
   *
   * Wrapped in try/catch so the admin settings page does not white-screen
   * when the module is freshly installed and tables are being created.
   */
  public function getLatestIndexVersion(): string {
    try {
      $result = $this->database->select('dcpas_chatbot_index_versions', 'v')
        ->fields('v', ['version', 'indexed_at'])
        ->orderBy('id', 'DESC')
        ->range(0, 1)
        ->execute()
        ->fetchAssoc();
      return $result ? "{$result['version']} ({$result['indexed_at']})" : 'no index yet';
    }
    catch (\Exception $e) {
      return 'unavailable';
    }
  }

  /**
   * Return total chunk and embedding counts.
   *
   * @return array{chunks: int, embedded: int}
   */
  public function getStats(): array {
    try {
      $chunks = (int) $this->database->select('dcpas_chatbot_chunks', 'c')
        ->countQuery()->execute()->fetchField();
      $embedded = (int) $this->database->select('dcpas_chatbot_embeddings', 'e')
        ->countQuery()->execute()->fetchField();
      return ['chunks' => $chunks, 'embedded' => $embedded];
    }
    catch (\Exception $e) {
      return ['chunks' => 0, 'embedded' => 0];
    }
  }

}
