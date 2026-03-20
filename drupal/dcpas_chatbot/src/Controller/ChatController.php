<?php

namespace Drupal\dcpas_chatbot\Controller;

use Drupal\Core\Config\ConfigFactoryInterface;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Flood\FloodInterface;
use Drupal\dcpas_chatbot\Service\AzureOpenAIClient;
use Drupal\dcpas_chatbot\Service\PromptBuilder;
use Drupal\dcpas_chatbot\Service\Retriever;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;

/**
 * Handles AJAX chat requests from the chatbot block.
 *
 * POST /api/dcpas-chatbot/chat
 * Body: { "question": "...", "token": "<CSRF token>" }
 * Response: { "answer": "...", "citations": [...], "error": null }
 *
 * Security controls:
 *  - CSRF token validation (Drupal session token)
 *  - Flood control (rate limiting per IP)
 *  - Input length cap
 *  - No internal error details exposed to the client
 */
class ChatController extends ControllerBase {

  /** Maximum allowed question length in characters. */
  const MAX_QUESTION_LENGTH = 500;

  public function __construct(
    protected readonly Retriever $retriever,
    protected readonly AzureOpenAIClient $openAIClient,
    protected readonly PromptBuilder $promptBuilder,
    protected readonly FloodInterface $flood,
    protected readonly ConfigFactoryInterface $configFactory,
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
    );
  }

  /**
   * Handle a POST chat request.
   *
   * @param \Symfony\Component\HttpFoundation\Request $request
   *
   * @return \Symfony\Component\HttpFoundation\JsonResponse
   */
  public function chat(Request $request): JsonResponse {
    $config = $this->configFactory->get('dcpas_chatbot.settings');

    // --- Guard: chatbot disabled ---
    if (!$config->get('enabled')) {
      return $this->errorResponse('The chatbot is currently unavailable.', 503);
    }

    // --- Guard: API key not configured ---
    if (empty($config->get('openai_api_key'))) {
      return $this->errorResponse('The chatbot is not configured yet.', 503);
    }

    // --- CSRF validation ---
    $body = json_decode($request->getContent(), TRUE) ?? [];
    $token = $body['token'] ?? '';
    if (!$this->csrfTokenValid($token)) {
      return $this->errorResponse('Invalid request token.', 403);
    }

    // --- Rate limiting ---
    $rateWindow = (int) ($config->get('rate_limit_window') ?? 60);
    $rateMax    = (int) ($config->get('rate_limit_max') ?? 10);
    $clientIp   = $request->getClientIp();

    if (!$this->flood->isAllowed('dcpas_chatbot.chat', $rateMax, $rateWindow, $clientIp)) {
      return $this->errorResponse('Too many requests. Please wait a moment.', 429);
    }
    $this->flood->register('dcpas_chatbot.chat', $rateWindow, $clientIp);

    // --- Parse and validate question ---
    $question = trim($body['question'] ?? '');
    if (empty($question)) {
      return $this->errorResponse('Please enter a question.', 400);
    }
    if (mb_strlen($question) > self::MAX_QUESTION_LENGTH) {
      return $this->errorResponse('Question is too long (max 500 characters).', 400);
    }
    // Strip tags to prevent prompt injection via HTML
    $question = strip_tags($question);

    // --- Retrieve + generate ---
    try {
      $chunks    = $this->retriever->retrieve($question);
      $system    = $this->promptBuilder->getSystemPrompt();
      $userMsg   = $this->promptBuilder->buildUserMessage($question, $chunks);
      $answer    = $this->openAIClient->complete($system, $userMsg);
      $citations = $this->promptBuilder->extractCitations($chunks);
    }
    catch (\RuntimeException $e) {
      // Log internally, return generic message to client
      \Drupal::logger('dcpas_chatbot')->error($e->getMessage());
      return $this->errorResponse('An error occurred while processing your question. Please try again.', 500);
    }

    // Fallback message if retrieval returned nothing
    if (empty($chunks)) {
      $answer = "I couldn't find relevant information in the DCPAS content to answer that question. Please try rephrasing, or visit dcpas.osd.mil directly.";
    }

    return new JsonResponse([
      'answer'    => $answer,
      'citations' => $citations,
      'error'     => NULL,
    ]);
  }

  /**
   * Build a standard error JSON response.
   */
  protected function errorResponse(string $message, int $status = 400): JsonResponse {
    return new JsonResponse(['answer' => NULL, 'citations' => [], 'error' => $message], $status);
  }

  /**
   * Validate the CSRF token from the request against the current session.
   */
  protected function csrfTokenValid(string $token): bool {
    if (empty($token)) {
      return FALSE;
    }
    return \Drupal::csrfToken()->validate($token, 'dcpas_chatbot_chat');
  }

}
