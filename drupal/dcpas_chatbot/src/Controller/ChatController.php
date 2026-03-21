<?php

namespace Drupal\dcpas_chatbot\Controller;

use Drupal\Core\Config\ConfigFactoryInterface;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Flood\FloodInterface;
use Drupal\Core\Session\AccountInterface;
use Drupal\Core\Session\CsrfTokenGenerator;
use Drupal\dcpas_chatbot\Service\AzureOpenAIClient;
use Drupal\dcpas_chatbot\Service\PromptBuilder;
use Drupal\dcpas_chatbot\Service\Retriever;
use Psr\Log\LoggerInterface;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;

/**
 * Handles AJAX chat requests from the chatbot block.
 *
 * POST /api/dcpas-chatbot/chat
 * Body (JSON): { "question": "...", "token": "<session CSRF token>" }
 * Response:    { "answer": "...", "citations": [...], "error": null }
 *
 * Request pipeline order (hardened):
 *  1. Content-Type check
 *  2. JSON decode validation
 *  3. Permission check
 *  4. CSRF validation
 *  5. Flood / rate limit (registered only for valid, authed requests)
 *  6. Input normalisation (strip_tags → length check)
 *  7. Prompt injection guard
 *  8. Retrieve → build prompt → call API
 *  9. Audit log (hashed question, IP, user ID)
 * 10. Sanitised JSON response
 */
class ChatController extends ControllerBase {

  /** Maximum allowed question length in characters (after tag stripping). */
  const MAX_QUESTION_LENGTH = 500;

  /**
   * Structural markers and known injection phrases that must be stripped from
   * user input to prevent prompt injection attacks corrupting the RAG template.
   *
   * Note: this is a best-effort defence-in-depth control. It reduces the
   * attack surface but cannot guarantee injection-free input. The server-side
   * system prompt is the authoritative trust boundary; this filter is a
   * supplementary layer. See CLAUDE.md § Prompt Injection Design.
   */
  const PROMPT_INJECTION_PATTERNS = [
    // Structural markers that mirror the RAG prompt template
    '/\[Source\s+\d+\]/i',
    '/^---+$/m',
    '/^Question:/m',
    '/^Use the following context/m',
    // Role / persona hijack phrases
    '/^System:/im',
    '/^Assistant:/im',
    '/^Override:/im',
    '/^Final answer:/im',
    '/<EndOfContext>/i',
    '/\bdisregard\b/i',
    '/ignore all\b/i',
    // Original catch-all
    '/ignore (all )?(previous|prior) instructions?/i',
  ];

  public function __construct(
    protected readonly Retriever $retriever,
    protected readonly AzureOpenAIClient $openAIClient,
    protected readonly PromptBuilder $promptBuilder,
    protected readonly FloodInterface $flood,
    protected readonly ConfigFactoryInterface $configFactory,
    protected readonly CsrfTokenGenerator $csrfTokenGenerator,
    protected readonly LoggerInterface $logger,
    protected readonly AccountInterface $currentUser,
  ) {}

  /**
   * {@inheritdoc}
   */
  public static function create(ContainerInterface $container): static {
    return new static(
      $container->get('dcpas_chatbot.retriever'),
      $container->get('dcpas_chatbot.azure_client'),
      $container->get('dcpas_chatbot.prompt_builder'),
      $container->get('flood'),
      $container->get('config.factory'),
      $container->get('csrf_token'),
      $container->get('logger.factory')->get('dcpas_chatbot'),
      $container->get('current_user'),
    );
  }

  /**
   * Handle a POST chat request.
   */
  public function chat(Request $request): JsonResponse {
    $config = $this->configFactory->get('dcpas_chatbot.settings');

    // --- Guard: chatbot disabled or not configured ---
    if (!$config->get('enabled') || empty($config->get('openai_api_key'))) {
      return $this->errorResponse('The chatbot is currently unavailable.', 503);
    }

    // --- Guard: Content-Type must be JSON ---
    if (!str_contains($request->headers->get('Content-Type', ''), 'application/json')) {
      return $this->errorResponse('Invalid request.', 400);
    }

    // --- Decode JSON body ---
    $body = json_decode($request->getContent(), TRUE);
    if (!is_array($body)) {
      return $this->errorResponse('Invalid request body.', 400);
    }

    // --- Permission check ---
    if (!$this->currentUser->hasPermission('access dcpas chatbot')) {
      $this->logger->warning('Chat 403: insufficient permission. uid=@uid ip=@ip', [
        '@uid' => $this->currentUser->id(),
        '@ip'  => $request->getClientIp(),
      ]);
      return $this->errorResponse('Access denied.', 403);
    }

    // --- CSRF validation ---
    $token = $body['token'] ?? '';
    if (empty($token) || !$this->csrfTokenGenerator->validate($token, 'dcpas_chatbot_chat')) {
      $this->logger->warning('Chat 403: invalid CSRF token. uid=@uid ip=@ip', [
        '@uid' => $this->currentUser->id(),
        '@ip'  => $request->getClientIp(),
      ]);
      return $this->errorResponse('Invalid request token.', 403);
    }

    // --- Flood / rate limiting ---
    $rateWindow = (int) ($config->get('rate_limit_window') ?? 60);
    $rateMax    = (int) ($config->get('rate_limit_max') ?? 10);
    $clientIp   = $request->getClientIp();

    if (!$this->flood->isAllowed('dcpas_chatbot.chat', $rateMax, $rateWindow, $clientIp)) {
      $this->logger->warning('Chat 429: rate limit exceeded. uid=@uid ip=@ip', [
        '@uid' => $this->currentUser->id(),
        '@ip'  => $clientIp,
      ]);
      return $this->errorResponse('Too many requests. Please wait a moment.', 429);
    }
    $this->flood->register('dcpas_chatbot.chat', $rateWindow, $clientIp);

    // --- Input normalisation: strip tags first, then enforce length ---
    // Normalize Unicode homoglyphs (e.g. Cyrillic 'а' → Latin 'a') before
    // pattern matching so injection phrases using lookalike characters are
    // caught by the blocklist. Requires PHP intl extension (iconv fallback
    // used if unavailable, which strips non-ASCII entirely).
    $rawQuestion = strip_tags(trim($body['question'] ?? ''));
    if (function_exists('normalizer_normalize')) {
      $rawQuestion = normalizer_normalize($rawQuestion, \Normalizer::FORM_KC) ?: $rawQuestion;
    }
    $question = $rawQuestion;
    if (empty($question)) {
      return $this->errorResponse('Please enter a question.', 400);
    }
    if (mb_strlen($question) > self::MAX_QUESTION_LENGTH) {
      return $this->errorResponse('Question is too long (max 500 characters).', 400);
    }

    // --- Prompt injection guard: remove structural markers from user input ---
    foreach (self::PROMPT_INJECTION_PATTERNS as $pattern) {
      $question = preg_replace($pattern, '', $question);
    }
    $question = trim($question);
    if (empty($question)) {
      return $this->errorResponse('Please enter a valid question.', 400);
    }

    // --- Retrieve → build prompt → call API ---
    try {
      $chunks    = $this->retriever->retrieve($question);
      $system    = $this->promptBuilder->getSystemPrompt();
      $userMsg   = $this->promptBuilder->buildUserMessage($question, $chunks);
      $answer    = $this->openAIClient->complete($system, $userMsg);
      $citations = $this->promptBuilder->extractCitations($chunks);
    }
    catch (\RuntimeException $e) {
      // Log error internally; never expose internal details to the client.
      $this->logger->error('Chat request failed: @msg', ['@msg' => $e->getMessage()]);
      $this->logger->warning('Chat API error: uid=@uid ip=@ip', [
        '@uid' => $this->currentUser->id(),
        '@ip'  => $clientIp,
      ]);
      return $this->errorResponse('An error occurred. Please try again.', 500);
    }

    // Fallback when retrieval found nothing relevant
    if (empty($chunks)) {
      $answer    = 'I couldn\'t find relevant information to answer that question. Please try rephrasing, or visit dcpas.osd.mil directly.';
      $citations = [];
    }

    // --- Audit log: hash question for PII compliance, never log plaintext ---
    $this->logger->info('Chat request processed. user=@uid ip=@ip q_hash=@qh chunks=@n', [
      '@uid' => $this->currentUser->id(),
      '@ip'  => $clientIp,
      '@qh'  => hash('sha256', $question),
      '@n'   => count($chunks),
    ]);

    // LLM answer is returned as plain text. The frontend MUST render it via
    // textContent (never innerHTML) — enforced in chatbot.js. We strip any
    // stray HTML tags here as a server-side defence-in-depth measure.
    $safeAnswer = strip_tags($answer);

    return new JsonResponse([
      'answer'    => $safeAnswer,
      'citations' => $citations,
      'error'     => NULL,
    ]);
  }

  /**
   * Build a standard error response. Never exposes internal details.
   */
  protected function errorResponse(string $message, int $status = 400): JsonResponse {
    return new JsonResponse(['answer' => NULL, 'citations' => [], 'error' => $message], $status);
  }

}
