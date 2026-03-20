<?php

namespace Drupal\dcpas_chatbot\Service;

use Drupal\Core\Config\ConfigFactoryInterface;
use GuzzleHttp\ClientInterface;
use GuzzleHttp\Exception\RequestException;

/**
 * HTTP client for OpenAI and Azure OpenAI APIs.
 *
 * Supports both standard OpenAI (api.openai.com) and Azure OpenAI endpoints.
 * Azure mode is activated when openai_api_version is set or the base URL
 * contains 'azure.com'. See config at Admin > Config > DCPAS Chatbot Settings.
 *
 * All API secrets come from Drupal config — never hardcoded here.
 */
class AzureOpenAIClient {

  /** @var array Loaded settings. */
  protected array $settings;

  /** @var bool Whether we are in Azure OpenAI mode. */
  protected bool $isAzure;

  public function __construct(
    protected readonly ConfigFactoryInterface $configFactory,
    protected readonly ClientInterface $httpClient,
  ) {
    $config = $this->configFactory->get('dcpas_chatbot.settings');
    $this->settings = [
      'api_key'     => $config->get('openai_api_key') ?? '',
      'api_base'    => rtrim($config->get('openai_api_base') ?? 'https://api.openai.com/v1', '/'),
      'api_version' => $config->get('openai_api_version') ?? '',
      'embed_model' => $config->get('embedding_model') ?? 'text-embedding-3-small',
      'chat_model'  => $config->get('chat_model') ?? 'gpt-4o',
      'max_tokens'  => (int) ($config->get('max_response_tokens') ?? 800),
    ];
    $this->isAzure = str_contains($this->settings['api_base'], 'azure.com')
      || !empty($this->settings['api_version']);
  }

  /**
   * Generate an embedding vector for the given text.
   *
   * @param string $text  The text to embed.
   *
   * @return float[]  The embedding vector.
   *
   * @throws \RuntimeException On API failure.
   */
  public function embed(string $text): array {
    $url = $this->buildEmbeddingUrl();
    $payload = [
      'input' => $text,
      'model' => $this->settings['embed_model'],
    ];
    $response = $this->request('POST', $url, $payload);
    $data = json_decode($response, TRUE);
    if (empty($data['data'][0]['embedding'])) {
      throw new \RuntimeException('Embeddings API returned unexpected structure.');
    }
    return $data['data'][0]['embedding'];
  }

  /**
   * Generate a chat completion.
   *
   * @param string $systemPrompt  Instruction context.
   * @param string $userMessage   The user's question (with RAG context injected).
   *
   * @return string  The assistant response text.
   *
   * @throws \RuntimeException On API failure.
   */
  public function complete(string $systemPrompt, string $userMessage): string {
    $url = $this->buildChatUrl();
    $payload = [
      'model'      => $this->settings['chat_model'],
      'max_tokens' => $this->settings['max_tokens'],
      'messages'   => [
        ['role' => 'system', 'content' => $systemPrompt],
        ['role' => 'user',   'content' => $userMessage],
      ],
    ];
    $response = $this->request('POST', $url, $payload);
    $data = json_decode($response, TRUE);
    if (empty($data['choices'][0]['message']['content'])) {
      throw new \RuntimeException('Chat API returned unexpected structure.');
    }
    return trim($data['choices'][0]['message']['content']);
  }

  /**
   * Build the embeddings endpoint URL.
   */
  protected function buildEmbeddingUrl(): string {
    if ($this->isAzure) {
      $version = $this->settings['api_version'] ?: '2024-02-01';
      $deployment = $this->settings['embed_model'];
      return "{$this->settings['api_base']}/deployments/{$deployment}/embeddings?api-version={$version}";
    }
    return "{$this->settings['api_base']}/embeddings";
  }

  /**
   * Build the chat completions endpoint URL.
   */
  protected function buildChatUrl(): string {
    if ($this->isAzure) {
      $version = $this->settings['api_version'] ?: '2024-02-01';
      $deployment = $this->settings['chat_model'];
      return "{$this->settings['api_base']}/deployments/{$deployment}/chat/completions?api-version={$version}";
    }
    return "{$this->settings['api_base']}/chat/completions";
  }

  /**
   * Send an authenticated JSON request to the API.
   *
   * @throws \RuntimeException On HTTP or network failure.
   */
  protected function request(string $method, string $url, array $payload): string {
    $headers = ['Content-Type' => 'application/json'];
    if ($this->isAzure) {
      $headers['api-key'] = $this->settings['api_key'];
    }
    else {
      $headers['Authorization'] = 'Bearer ' . $this->settings['api_key'];
    }

    try {
      $response = $this->httpClient->request($method, $url, [
        'headers' => $headers,
        'json'    => $payload,
        'timeout' => 30,
      ]);
      return (string) $response->getBody();
    }
    catch (RequestException $e) {
      $code = $e->getResponse() ? $e->getResponse()->getStatusCode() : 'N/A';
      // Do not expose the full body — it may contain internal details.
      throw new \RuntimeException("OpenAI API error (HTTP {$code}). Check API key and settings.", 0, $e);
    }
  }

}
