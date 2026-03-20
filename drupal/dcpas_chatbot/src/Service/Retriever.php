<?php

namespace Drupal\dcpas_chatbot\Service;

use Drupal\Core\Config\ConfigFactoryInterface;

/**
 * Retrieves the top-K most relevant chunks for a user query.
 *
 * Flow: embed query → load corpus → cosine similarity → score filter → top-K.
 *
 * Config values are read fresh on each retrieve() call so changes to top_k
 * and min_score via the admin UI take effect immediately without a cache flush.
 */
class Retriever {

  public function __construct(
    protected readonly VectorStore $vectorStore,
    protected readonly AzureOpenAIClient $openAIClient,
    protected readonly ConfigFactoryInterface $configFactory,
  ) {}

  /**
   * Find the most relevant chunks for a query string.
   *
   * @param string $query   The user's question (pre-sanitised by ChatController).
   * @param int    $topK    Override the configured top-K if > 0.
   *
   * @return array[]  Chunks sorted by descending similarity, each with:
   *                  chunk_id, source_url, title, text, score (float).
   *
   * @throws \RuntimeException If embedding the query fails.
   */
  public function retrieve(string $query, int $topK = 0): array {
    // Read config fresh so admin changes to top_k/min_score take effect
    // without requiring a Drupal cache rebuild.
    $config   = $this->configFactory->get('dcpas_chatbot.settings');
    $k        = $topK > 0 ? $topK : (int) ($config->get('top_k') ?? 5);
    $minScore = (float) ($config->get('min_score') ?? 0.70);

    $queryVector = $this->openAIClient->embed($query);
    $corpus      = $this->vectorStore->loadAllWithEmbeddings();

    if (empty($corpus)) {
      return [];
    }

    $scored = [];
    foreach ($corpus as $chunk) {
      $score = $this->cosineSimilarity($queryVector, $chunk['embedding']);
      // Apply minimum similarity threshold so low-relevance chunks are not
      // used as context. This prevents the model from generating confidently
      // wrong answers when no relevant content exists in the index.
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
    return array_slice($scored, 0, $k);
  }

  /**
   * Compute cosine similarity between two equal-length float vectors.
   *
   * @return float  Value in [-1, 1]. Returns 0.0 for zero-magnitude vectors
   *                or mismatched lengths.
   */
  protected function cosineSimilarity(array $a, array $b): float {
    if (count($a) !== count($b) || empty($a)) {
      return 0.0;
    }
    $dot = 0.0;
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
