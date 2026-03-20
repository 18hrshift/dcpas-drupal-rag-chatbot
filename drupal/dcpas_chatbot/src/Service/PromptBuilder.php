<?php

namespace Drupal\dcpas_chatbot\Service;

use Drupal\Core\Config\ConfigFactoryInterface;

/**
 * Constructs RAG prompts from a user question and retrieved chunks.
 *
 * Security notes:
 *  - Chunk text is wrapped in XML-style delimiters so injected content
 *    cannot escape the source block and corrupt the prompt structure
 *    (indirect prompt injection via poisoned corpus content).
 *  - Structural markers are stripped from chunk text before insertion.
 *  - Citation URLs are validated for http/https scheme before being
 *    returned to the frontend (prevents javascript:/data: URI injection).
 *  - System prompt is read fresh each call so admin changes take effect
 *    immediately without a cache flush.
 */
class PromptBuilder {

  /** Prompt structural markers to strip from corpus chunk text. */
  const STRUCTURAL_MARKERS = [
    '/\[Source\s+\d+\]/i',
    '/^---+$/m',
    '/^Question:/m',
    '/^Use the following context/m',
  ];

  public function __construct(
    protected readonly ConfigFactoryInterface $configFactory,
  ) {}

  /**
   * Return the current system prompt from config.
   */
  public function getSystemPrompt(): string {
    return $this->configFactory->get('dcpas_chatbot.settings')
      ->get('system_prompt') ?? '';
  }

  /**
   * Build the user-turn message that includes retrieved context.
   *
   * Context blocks are wrapped in <source> XML tags to prevent injected
   * content from escaping block boundaries and corrupting the prompt.
   *
   * @param string  $question  Pre-sanitised user question.
   * @param array[] $chunks    Retrieved chunks from Retriever::retrieve().
   *
   * @return string
   */
  public function buildUserMessage(string $question, array $chunks): string {
    if (empty($chunks)) {
      return "Question: {$question}\n\n(No relevant content was found in the index.)";
    }

    $contextParts = [];
    foreach ($chunks as $i => $chunk) {
      $n    = $i + 1;
      $url  = $this->sanitiseUrl($chunk['source_url']);
      $text = $this->sanitiseChunkText($chunk['text']);
      // XML-style delimiters make it harder for injected content to break
      // the prompt structure (indirect prompt injection via corpus content).
      $contextParts[] = "<source id=\"{$n}\" url=\"{$url}\">\n{$text}\n</source>";
    }
    $context = implode("\n\n", $contextParts);

    return <<<PROMPT
Use the following sources to answer the question. Cite sources by their id attribute.

{$context}

Question: {$question}
PROMPT;
  }

  /**
   * Extract a deduplicated, URL-validated list of citations from retrieved chunks.
   *
   * @param array[] $chunks  Retrieved chunks.
   *
   * @return array[]  List of ['title' => ..., 'url' => ...], deduped by URL.
   *                  Only http/https URLs are included.
   */
  public function extractCitations(array $chunks): array {
    $seen = [];
    $citations = [];
    foreach ($chunks as $chunk) {
      $url = $this->sanitiseUrl($chunk['source_url']);
      if ($url === '' || isset($seen[$url])) {
        continue;
      }
      $seen[$url] = TRUE;
      $citations[] = [
        'title' => $chunk['title'] ?: $url,
        'url'   => $url,
      ];
    }
    return $citations;
  }

  /**
   * Validate a URL and return it only if http/https.
   *
   * Returns empty string for invalid, javascript:, data:, or other
   * non-web schemes to prevent stored XSS via citation links.
   */
  protected function sanitiseUrl(string $url): string {
    if (!filter_var($url, FILTER_VALIDATE_URL)) {
      return '';
    }
    $scheme = parse_url($url, PHP_URL_SCHEME);
    if (!in_array($scheme, ['http', 'https'], TRUE)) {
      return '';
    }
    return $url;
  }

  /**
   * Strip prompt structural markers from chunk text before inserting into prompt.
   *
   * Prevents indirect prompt injection where adversarially crafted indexed
   * content could break the prompt structure or override instructions.
   */
  protected function sanitiseChunkText(string $text): string {
    foreach (self::STRUCTURAL_MARKERS as $pattern) {
      $text = preg_replace($pattern, '', $text);
    }
    return trim($text);
  }

}
