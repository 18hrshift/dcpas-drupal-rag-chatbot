<?php

namespace Drupal\dcpas_chatbot\Service;

/**
 * Contract for all vector store backends (SQLite and pgvector).
 *
 * Implementations must:
 *   - Perform similarity search (findSimilar) — either in-process (SQLite)
 *     or via the database engine (pgvector).
 *   - Provide stats, manifest, and index version for the admin UI and
 *     the Drush healthcheck command.
 *
 * Owned by: dcpas_chatbot.vector_store service (see services.yml).
 * Do not add business logic to implementations — Retriever owns retrieval
 * orchestration; implementations own only the backend-specific query.
 */
interface VectorStoreInterface {

  /**
   * Find the top-K chunks most similar to a query embedding vector.
   *
   * @param float[] $queryVector
   *   The query embedding produced by AzureOpenAIClient::embed().
   * @param int $topK
   *   Maximum number of chunks to return.
   * @param float $minScore
   *   Minimum cosine similarity threshold. Chunks below this are excluded.
   *
   * @return array[]
   *   Chunks sorted by descending similarity score, each with keys:
   *   chunk_id, source_url, title, text, score (float 0–1).
   */
  public function findSimilar(array $queryVector, int $topK, float $minScore): array;

  /**
   * Return total chunk and embedding counts.
   *
   * @return array{chunks: int, embedded: int}
   */
  public function getStats(): array;

  /**
   * Read the index manifest written by the ingestion pipeline.
   *
   * @return array|null
   *   Keys: run_at, total_chunks, embedded_chunks, skipped_poisoned,
   *   corpus_hash. Null if path not configured or file missing.
   */
  public function getManifest(): ?array;

  /**
   * Return the latest index version string, or a human-readable status.
   */
  public function getLatestIndexVersion(): string;

}
