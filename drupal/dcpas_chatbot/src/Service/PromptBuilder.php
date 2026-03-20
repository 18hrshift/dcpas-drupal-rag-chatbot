<?php

namespace Drupal\dcpas_chatbot\Service;

use Drupal\Core\Config\ConfigFactoryInterface;

/**
 * Constructs RAG prompts from a user question and retrieved chunks.
 *
 * Produces two outputs:
 *  - A user-turn message containing the question plus numbered context blocks.
 *  - A deduplicated list of source citations (title + URL).
 *
 * The system prompt is stored in Drupal config and editable by admins.
 */
class PromptBuilder {

  protected string $systemPrompt;

  public function __construct(
    protected readonly ConfigFactoryInterface $configFactory,
  ) {
    $this->systemPrompt = $configFactory->get('dcpas_chatbot.settings')
      ->get('system_prompt') ?? '';
  }

  /**
   * Build the system prompt string.
   *
   * @return string
   */
  public function getSystemPrompt(): string {
    return $this->systemPrompt;
  }

  /**
   * Build the user-turn message that includes retrieved context.
   *
   * Context blocks are numbered and separated so the model can reference them.
   * Each block ends with its source URL so the model can cite it.
   *
   * @param string  $question  The user's question.
   * @param array[] $chunks    Retrieved chunks from Retriever::retrieve().
   *
   * @return string  The complete user message for the API call.
   */
  public function buildUserMessage(string $question, array $chunks): string {
    if (empty($chunks)) {
      return "Question: {$question}\n\n(No relevant content was found in the index.)";
    }

    $contextParts = [];
    foreach ($chunks as $i => $chunk) {
      $n = $i + 1;
      $contextParts[] = "[Source {$n}] {$chunk['title']}\nURL: {$chunk['source_url']}\n\n{$chunk['text']}";
    }
    $context = implode("\n\n---\n\n", $contextParts);

    return <<<PROMPT
Use the following context to answer the question. Cite sources by their [Source N] number.

{$context}

---

Question: {$question}
PROMPT;
  }

  /**
   * Extract a deduplicated list of citation sources from the retrieved chunks.
   *
   * @param array[] $chunks  Retrieved chunks (each with source_url and title).
   *
   * @return array[]  List of ['title' => ..., 'url' => ...], deduped by URL.
   */
  public function extractCitations(array $chunks): array {
    $seen = [];
    $citations = [];
    foreach ($chunks as $chunk) {
      $url = $chunk['source_url'];
      if (!isset($seen[$url])) {
        $seen[$url] = TRUE;
        $citations[] = [
          'title' => $chunk['title'] ?: $url,
          'url'   => $url,
        ];
      }
    }
    return $citations;
  }

}
