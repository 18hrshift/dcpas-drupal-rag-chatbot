<?php

namespace Drupal\dcpas_chatbot\Service;

use Drupal\Core\Database\Connection;

/**
 * Reads chunk and embedding data from the Drupal MySQL database.
 *
 * The three tables (dcpas_chatbot_chunks, dcpas_chatbot_embeddings,
 * dcpas_chatbot_index_versions) are created by hook_schema() in
 * dcpas_chatbot.install and populated by the Python ingestion pipeline
 * via the export_mysql.py export script.
 *
 * All queries use Drupal's database API (parameterized) — no raw SQL
 * string interpolation anywhere in this class.
 */
class VectorStore {

  public function __construct(
    protected readonly Connection $database,
  ) {}

  /**
   * Load all chunks that have embeddings.
   *
   * Returns an array of associative arrays:
   *   chunk_id, source_url, title, text, embedding (float[])
   *
   * NOTE: Loads the full corpus into PHP memory. For demo-scale corpora
   * (~1000–5000 chunks) this is acceptable. Production deployments should
   * use a dedicated vector database (pgvector, Weaviate, etc.).
   *
   * @return array[]
   */
  public function loadAllWithEmbeddings(): array {
    $query = $this->database->select('dcpas_chatbot_chunks', 'c');
    $query->join('dcpas_chatbot_embeddings', 'e', 'c.chunk_id = e.chunk_id');
    $query->fields('c', ['chunk_id', 'source_url', 'title', 'text']);
    $query->fields('e', ['vector_json']);

    $results = [];
    foreach ($query->execute() as $row) {
      $vector = json_decode($row->vector_json, TRUE);
      if (!is_array($vector)) {
        continue;
      }
      $results[] = [
        'chunk_id'   => $row->chunk_id,
        'source_url' => $row->source_url,
        'title'      => $row->title,
        'text'       => $row->text,
        'embedding'  => $vector,
      ];
    }
    return $results;
  }

  /**
   * Return the latest index version string, or 'unknown' if none recorded.
   */
  public function getLatestIndexVersion(): string {
    $result = $this->database->select('dcpas_chatbot_index_versions', 'v')
      ->fields('v', ['version', 'indexed_at'])
      ->orderBy('id', 'DESC')
      ->range(0, 1)
      ->execute()
      ->fetchAssoc();
    return $result ? "{$result['version']} ({$result['indexed_at']})" : 'unknown';
  }

  /**
   * Return total chunk and embedding counts for the admin status display.
   *
   * @return array{chunks: int, embedded: int}
   */
  public function getStats(): array {
    $chunks = (int) $this->database->select('dcpas_chatbot_chunks', 'c')
      ->countQuery()->execute()->fetchField();
    $embedded = (int) $this->database->select('dcpas_chatbot_embeddings', 'e')
      ->countQuery()->execute()->fetchField();
    return ['chunks' => $chunks, 'embedded' => $embedded];
  }

}
