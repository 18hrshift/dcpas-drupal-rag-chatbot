<?php

namespace Drupal\dcpas_chatbot\Service;

use Drupal\Core\Config\ConfigFactoryInterface;

/**
 * Routes vector store calls to the configured backend.
 *
 * This service is registered as dcpas_chatbot.vector_store and is what all
 * consumers (Retriever, SettingsForm, DcpasChatbotCommands) receive. It reads
 * the vector_store_backend config on every call so the admin can switch
 * backends via the settings UI without a Drupal cache rebuild.
 *
 * Backends:
 *   sqlite   — SqliteVectorStore (default, in-process cosine similarity)
 *   pgvector — PgVectorStore (PostgreSQL + pgvector extension)
 */
class VectorStoreLocator implements VectorStoreInterface {

  public function __construct(
    private readonly SqliteVectorStore $sqlite,
    private readonly PgVectorStore $pg,
    private readonly ConfigFactoryInterface $configFactory,
  ) {}

  /**
   * Return the active backend based on current config.
   */
  private function backend(): VectorStoreInterface {
    $backend = $this->configFactory
      ->get('dcpas_chatbot.settings')
      ->get('vector_store_backend') ?? 'sqlite';
    return $backend === 'pgvector' ? $this->pg : $this->sqlite;
  }

  /**
   * {@inheritdoc}
   */
  public function findSimilar(array $queryVector, int $topK, float $minScore): array {
    return $this->backend()->findSimilar($queryVector, $topK, $minScore);
  }

  /**
   * {@inheritdoc}
   */
  public function getStats(): array {
    return $this->backend()->getStats();
  }

  /**
   * {@inheritdoc}
   */
  public function getManifest(): ?array {
    return $this->backend()->getManifest();
  }

  /**
   * {@inheritdoc}
   */
  public function getLatestIndexVersion(): string {
    return $this->backend()->getLatestIndexVersion();
  }

}
