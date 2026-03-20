<?php

namespace Drupal\dcpas_chatbot\Service;

use Drupal\Core\Config\ConfigFactoryInterface;
use GuzzleHttp\ClientInterface;
use GuzzleHttp\Exception\RequestException;

/**
 * HTTP client for OpenAI and Azure OpenAI APIs.
 *
 * Security hardening:
 *  - API key is never cached in memory; read fresh from config on each call
 *    so key rotations take effect without a cache rebuild.
 *  - getenv('DCPAS_OPENAI_API_KEY') takes precedence over Drupal config,
 *    allowing secrets to be managed by the server environment / Vault without
 *    storing them in the database at all.
 *  - All API calls enforce TLS certificate verification (verify: true).
 *  - HTTPS-only URLs enforced before every request.
 *  - Exception chain is NOT forwarded to callers to prevent Azure diagnostic
 *    information (tenant ID, resource names) from leaking into logs.
 *  - Provider type is an explicit config value, not inferred from URL patterns.
 */
class AzureOpenAIClient {

  public function __construct(
    protected readonly ConfigFactoryInterface $configFactory,
    protected readonly ClientInterface $httpClient,
  ) {}

  /**
   * Generate an embedding vector for the given text.
   *
   * @param string $text  Text to embed (max 8 000 characters).
   *
   * @return float[]
   *
   * @throws \RuntimeException on API failure.
   * @throws \InvalidArgumentException on empty or over-length input.
   */
  public function embed(string $text): array {
    if (empty(trim($text))) {
      throw new \InvalidArgumentException('Cannot embed empty text.');
    }
    // Guard against token-limit overruns (~8 000 chars ≈ 2 000 tokens).
    $text = mb_substr($text, 0, 8000);

    $settings = $this->getSettings();
    $url      = $this->buildEmbeddingUrl($settings);
    $payload  = [
      'input' => $text,
      'model' => $settings['embed_model'],
    ];

    $response = $this->request('POST', $url, $payload, $settings);
    $data     = json_decode($response, TRUE);

    if (empty($data['data'][0]['embedding'])) {
      throw new \RuntimeException('Embeddings API returned unexpected structure.');
    }
    return $data['data'][0]['embedding'];
  }

  /**
   * Generate a chat completion.
   *
   * @param string $systemPrompt  Instruction context for the model.
   * @param string $userMessage   User turn (with RAG context injected by PromptBuilder).
   *
   * @return string  The assistant response text.
   *
   * @throws \RuntimeException on API failure.
   */
  public function complete(string $systemPrompt, string $userMessage): string {
    $settings = $this->getSettings();
    $url      = $this->buildChatUrl($settings);
    $payload  = [
      'model'      => $settings['chat_model'],
      'max_tokens' => $settings['max_tokens'],
      'messages'   => [
        ['role' => 'system', 'content' => $systemPrompt],
        ['role' => 'user',   'content' => $userMessage],
      ],
    ];

    $response = $this->request('POST', $url, $payload, $settings);
    $data     = json_decode($response, TRUE);

    if (empty($data['choices'][0]['message']['content'])) {
      throw new \RuntimeException('Chat API returned unexpected structure.');
    }
    return trim($data['choices'][0]['message']['content']);
  }

  /**
   * Read current settings fresh from config (and environment).
   *
   * Reading fresh on each call ensures that API key rotations and config
   * changes are picked up without requiring a Drupal cache rebuild.
   */
  protected function getSettings(): array {
    $config = $this->configFactory->get('dcpas_chatbot.settings');

    $apiBase = rtrim($config->get('openai_api_base') ?? 'https://api.openai.com/v1', '/');

    return [
      // Environment variable takes precedence over Drupal config.
      // Set DCPAS_OPENAI_API_KEY on the server to keep secrets out of the DB.
      'api_key'     => getenv('DCPAS_OPENAI_API_KEY') ?: ($config->get('openai_api_key') ?? ''),
      'api_base'    => $apiBase,
      'api_version' => $config->get('openai_api_version') ?? '',
      'provider'    => $config->get('provider') ?? 'openai',  // 'openai' or 'azure'
      'embed_model' => $config->get('embedding_model') ?? 'text-embedding-3-small',
      'chat_model'  => $config->get('chat_model') ?? 'gpt-4o',
      'max_tokens'  => (int) ($config->get('max_response_tokens') ?? 800),
      'timeout'     => (int) ($config->get('api_timeout') ?? 15),
    ];
  }

  /**
   * Build the embeddings endpoint URL.
   */
  protected function buildEmbeddingUrl(array $settings): string {
    if ($settings['provider'] === 'azure') {
      $version    = $settings['api_version'] ?: '2024-02-01';
      $deployment = $settings['embed_model'];
      return "{$settings['api_base']}/deployments/{$deployment}/embeddings?api-version={$version}";
    }
    return "{$settings['api_base']}/embeddings";
  }

  /**
   * Build the chat completions endpoint URL.
   */
  protected function buildChatUrl(array $settings): string {
    if ($settings['provider'] === 'azure') {
      $version    = $settings['api_version'] ?: '2024-02-01';
      $deployment = $settings['chat_model'];
      return "{$settings['api_base']}/deployments/{$deployment}/chat/completions?api-version={$version}";
    }
    return "{$settings['api_base']}/chat/completions";
  }

  /**
   * Send an authenticated JSON request to the API.
   *
   * @throws \RuntimeException on HTTP or network failure (no chain — prevents
   *   Azure diagnostic data from leaking through exception chains).
   */
  protected function request(string $method, string $url, array $payload, array $settings): string {
    // Enforce HTTPS-only regardless of what is stored in config.
    if (!str_starts_with($url, 'https://')) {
      throw new \RuntimeException('API requests must use HTTPS. Check the API base URL in settings.');
    }

    $headers = ['Content-Type' => 'application/json'];
    if ($settings['provider'] === 'azure') {
      $headers['api-key'] = $settings['api_key'];
    }
    else {
      $headers['Authorization'] = 'Bearer ' . $settings['api_key'];
    }

    try {
      $response = $this->httpClient->request($method, $url, [
        'headers' => $headers,
        'json'    => $payload,
        'timeout' => $settings['timeout'],
        'verify'  => TRUE,  // Always enforce TLS certificate verification.
      ]);
      return (string) $response->getBody();
    }
    catch (RequestException $e) {
      $code = $e->getResponse() ? $e->getResponse()->getStatusCode() : 'N/A';
      // Do NOT chain $e — the Guzzle exception may contain the raw Azure response
      // body, which can include tenant IDs and resource names.
      throw new \RuntimeException("OpenAI API error (HTTP {$code}). Check API key and settings.");
    }
  }

}
