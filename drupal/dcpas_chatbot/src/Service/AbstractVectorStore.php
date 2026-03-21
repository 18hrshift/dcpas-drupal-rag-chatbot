<?php

namespace Drupal\dcpas_chatbot\Service;

use Drupal\Core\Config\ConfigFactoryInterface;
use Drupal\Core\Database\Connection;
use Psr\Log\LoggerInterface;

/**
 * Shared DB/manifest/stats methods used by all vector store backends.
 *
 * Both SqliteVectorStore and PgVectorStore extend this class.
 * Backend-specific retrieval logic lives in findSimilar() in the subclass.
 */
abstract class AbstractVectorStore implements VectorStoreInterface {

  public function __construct(
    protected readonly Connection $database,
    protected readonly ConfigFactoryInterface $configFactory,
    protected readonly LoggerInterface $logger,
  ) {}

  /**
   * {@inheritdoc}
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
   * {@inheritdoc}
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
   * {@inheritdoc}
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
   * Parse PHP memory_limit string (e.g. "256M", "1G") to bytes.
   *
   * Returns 0 if unlimited (-1) or unparseable.
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
