<?php

namespace Drupal\dcpas_chatbot\Service;

use Drupal\Core\Config\ConfigFactoryInterface;
use Drupal\Core\Database\Connection;
use Psr\Log\LoggerInterface;

/**
 * Reads chunk and embedding data from the Drupal MySQL database.
 *
 * Memory safety: loadAllWithEmbeddings() loads the corpus in batches of
 * LOAD_BATCH_SIZE rows. Before each batch it checks memory_get_usage() and
 * stops early (with a warning log) if usage approaches MEMORY_CEILING_FRACTION
 * of PHP's memory_limit. The configurable max_chunks setting is the normal
 * operational cap; ABSOLUTE_ROW_CAP is the hard ceiling regardless of config.
 *
 * For production FedRAMP deployments exceeding the memory ceiling, replace
 * with pgvector, Azure Cognitive Search, or a dedicated vector database.
 * See CLAUDE.md § Memory Safety and ROADMAP Sprint 8.
 */
class VectorStore {

  /**
   * Hard row cap — absolute ceiling regardless of max_chunks config.
   * See CLAUDE.md § Memory Safety for rationale.
   */
  const ABSOLUTE_ROW_CAP = 50000;

  /** Batch size for memory-safe chunk loading. */
  const LOAD_BATCH_SIZE = 1000;

  /**
   * Memory safety threshold: stop loading if usage exceeds this fraction of
   * PHP's memory_limit. 0.80 = stop at 80 % of memory_limit.
   */
  const MEMORY_CEILING_FRACTION = 0.80;

  public function __construct(
    protected readonly Connection $database,
    protected readonly ConfigFactoryInterface $configFactory,
    protected readonly LoggerInterface $logger,
  ) {}

  /**
   * Load all chunks that have embeddings.
   *
   * Loads in batches of LOAD_BATCH_SIZE. Stops early if the PHP memory
   * ceiling is approached, logging a warning so admins know retrieval is
   * operating on a truncated corpus.
   *
   * Returns an array of associative arrays:
   *   chunk_id, source_url, title, text, embedding (float[])
   *
   * @return array[]
   */
  public function loadAllWithEmbeddings(): array {
    $config   = $this->configFactory->get('dcpas_chatbot.settings');
    $maxChunks = min(
      (int) ($config->get('max_chunks') ?? 10000),
      self::ABSOLUTE_ROW_CAP
    );
    $memLimit = $this->parseMemoryLimit(ini_get('memory_limit'));

    $results = [];
    $offset  = 0;

    while (TRUE) {
      // Memory ceiling guard: stop before exhausting PHP memory.
      if ($memLimit > 0 && memory_get_usage(TRUE) > $memLimit * self::MEMORY_CEILING_FRACTION) {
        $this->logger->warning(
          'VectorStore: memory ceiling reached at @n chunks loaded (@used / @limit bytes). ' .
          'Retrieval will operate on a partial corpus. ' .
          'Lower max_chunks or migrate to pgvector for larger corpora.',
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
        // Skip corrupt rows where the vector is missing or non-numeric.
        if (!is_array($vector) || empty($vector)) {
          continue;
        }
        // Validate that all vector elements are finite numerics to prevent PHP
        // arithmetic errors in cosineSimilarity(). Explicitly reject INF and NaN
        // values that pass is_float() but corrupt cosine similarity calculations.
        foreach ($vector as $v) {
          if (!is_float($v) && !is_int($v)) {
            continue 2;
          }
          if (is_infinite($v) || is_nan($v)) {
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

      $offset += $batchSize;
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
   * Read the index manifest file written by the ingestion pipeline.
   *
   * Returns null if the path is not configured or the file does not exist.
   *
   * @return array|null Array with keys: run_at, total_chunks, embedded_chunks,
   *   skipped_poisoned, corpus_hash. Null if unavailable.
   */
  public function getManifest(): ?array {
    $config = $this->configFactory->get('dcpas_chatbot.settings');
    $path   = $config->get('manifest_path');
    if (empty($path) || !file_exists($path)) {
      return NULL;
    }
    $content = @file_get_contents($path);
    if ($content === FALSE) {
      return NULL;
    }
    $data = json_decode($content, TRUE);
    return is_array($data) ? $data : NULL;
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

  /**
   * Parse PHP memory_limit string (e.g. "256M", "1G") to bytes.
   *
   * Returns 0 if the limit is -1 (unlimited) or unparseable.
   */
  protected function parseMemoryLimit(string $limit): int {
    if ($limit === '-1') {
      return 0;
    }
    $unit  = strtoupper(substr($limit, -1));
    $value = (int) $limit;
    return match ($unit) {
      'G' => $value * 1024 * 1024 * 1024,
      'M' => $value * 1024 * 1024,
      'K' => $value * 1024,
      default => $value,
    };
  }

}
