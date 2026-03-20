<?php

namespace Drupal\dcpas_chatbot\Service;

use Drupal\Core\Config\ConfigFactoryInterface;

/**
 * Retrieves the top-K most relevant chunks for a user query.
 *
 * Flow: embed query → load corpus → cosine similarity → return top-K.
 *
 * Cosine similarity is computed in PHP over the full corpus. This is O(n)
 * in memory and CPU per request and is suitable for demo-scale corpora.
 */
class Retriever {

  protected int $topK;

  public function __construct(
    protected readonly VectorStore $vectorStore,
    protected readonly AzureOpenAIClient $openAIClient,
    protected readonly ConfigFactoryInterface $configFactory,
  ) {
    $this->topK = (int) ($configFactory->get('dcpas_chatbot.settings')->get('top_k') ?? 5);
  }

  /**
   * Find the most relevant chunks for a query string.
   *
   * @param string $query   The user's question.
   * @param int    $topK    Override the configured top-K if provided.
   *
   * @return array[]  Chunks sorted by descending similarity, each with:
   *                  chunk_id, source_url, title, text, score (float).
   *
   * @throws \RuntimeException If embedding the query fails.
   */
  public function retrieve(string $query, int $topK = 0): array {
    $k = $topK > 0 ? $topK : $this->topK;

    $queryVector = $this->openAIClient->embed($query);
    $corpus = $this->vectorStore->loadAllWithEmbeddings();

    if (empty($corpus)) {
      return [];
    }

    $scored = [];
    foreach ($corpus as $chunk) {
      $score = $this->cosineSimilarity($queryVector, $chunk['embedding']);
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
   * @return float  Value in [-1, 1]. Returns 0.0 for zero-magnitude vectors.
   */
  protected function cosineSimilarity(array $a, array $b): float {
    if (count($a) !== count($b)) {
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
