<?php

namespace Drupal\dcpas_chatbot\Service;

use Drupal\Core\Config\ConfigFactoryInterface;

/**
 * Retrieves the top-K most relevant chunks for a user query.
 *
 * Flow: embed query → delegate similarity search to VectorStoreInterface
 * (SQLite in-process cosine or pgvector ANN, depending on backend config).
 *
 * Config values are read fresh on each retrieve() call so changes to top_k
 * and min_score via the admin UI take effect immediately without a cache flush.
 *
 * Similarity search logic is owned by the vector store backend, not here.
 * See SqliteVectorStore::findSimilar() and PgVectorStore::findSimilar().
 */
class Retriever {

  public function __construct(
    protected readonly VectorStoreInterface $vectorStore,
    protected readonly AzureOpenAIClient $openAIClient,
    protected readonly ConfigFactoryInterface $configFactory,
  ) {}

  /**
   * Find the most relevant chunks for a query string.
   *
   * @param string $query  The user's question (pre-sanitised by ChatController).
   * @param int    $topK   Override the configured top-K if > 0.
   *
   * @return array[]  Chunks sorted by descending similarity, each with:
   *                  chunk_id, source_url, title, text, score (float).
   *
   * @throws \RuntimeException If embedding the query fails.
   */
  public function retrieve(string $query, int $topK = 0): array {
    $config   = $this->configFactory->get('dcpas_chatbot.settings');
    $k        = $topK > 0 ? $topK : (int) ($config->get('top_k') ?? 5);
    $minScore = (float) ($config->get('min_score') ?? 0.70);

    $queryVector = $this->openAIClient->embed($query);
    return $this->vectorStore->findSimilar($queryVector, $k, $minScore);
  }

}
