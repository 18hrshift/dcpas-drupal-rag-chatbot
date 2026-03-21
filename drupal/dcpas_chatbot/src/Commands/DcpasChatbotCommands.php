<?php

namespace Drupal\dcpas_chatbot\Commands;

use Drupal\Core\Config\ConfigFactoryInterface;
use Drupal\dcpas_chatbot\Service\VectorStore;
use Drush\Commands\DrushCommands;

/**
 * Drush commands for DCPAS Chatbot operations.
 *
 * Usage:
 *   drush dcpas:healthcheck        — verify config, index, and Azure connectivity
 */
class DcpasChatbotCommands extends DrushCommands {

  public function __construct(
    protected readonly ConfigFactoryInterface $configFactory,
    protected readonly VectorStore $vectorStore,
  ) {
    parent::__construct();
  }

  /**
   * Verify chatbot configuration, index health, and Azure connectivity.
   *
   * Checks:
   *   1. Chatbot is enabled
   *   2. API key is set (config or env var)
   *   3. API base URL is configured and uses HTTPS
   *   4. Index is populated (chunks + embeddings > 0)
   *   5. Manifest file is present (if path configured)
   *   6. Azure/OpenAI connectivity (live ping via embeddings endpoint)
   *
   * Exit code 0 = all checks passed.
   * Exit code 1 = one or more checks failed.
   *
   * @command dcpas:healthcheck
   * @aliases dcpas-health
   * @usage drush dcpas:healthcheck
   *   Run all health checks and report status.
   */
  public function healthcheck(): void {
    $config  = $this->configFactory->get('dcpas_chatbot.settings');
    $passed  = 0;
    $failed  = 0;

    $check = function (string $label, bool $ok, string $detail = '') use (&$passed, &$failed): void {
      $icon = $ok ? '✓' : '✗';
      $line = "  [{$icon}] {$label}";
      if ($detail) {
        $line .= " — {$detail}";
      }
      if ($ok) {
        $this->output()->writeln("<info>{$line}</info>");
        $passed++;
      }
      else {
        $this->output()->writeln("<error>{$line}</error>");
        $failed++;
      }
    };

    $this->output()->writeln('<comment>DCPAS Chatbot Health Check</comment>');
    $this->output()->writeln('');

    // 1. Chatbot enabled
    $check('Chatbot enabled', (bool) $config->get('enabled'));

    // 2. API key present
    $envKey    = getenv('DCPAS_OPENAI_API_KEY');
    $configKey = $config->get('openai_api_key');
    $keySet    = !empty($envKey) || !empty($configKey);
    $keySource = !empty($envKey) ? 'env var (DCPAS_OPENAI_API_KEY)' : 'Drupal config';
    $check('API key configured', $keySet, $keySet ? "source: {$keySource}" : 'set DCPAS_OPENAI_API_KEY or configure via admin UI');

    // 3. API base URL
    $apiBase = $config->get('openai_api_base') ?? '';
    $baseOk  = !empty($apiBase) && str_starts_with($apiBase, 'https://');
    $check('API base URL set (HTTPS)', $baseOk, $baseOk ? $apiBase : 'missing or not HTTPS');

    // 4. Index populated
    $stats   = $this->vectorStore->getStats();
    $hasData = $stats['chunks'] > 0 && $stats['embedded'] > 0;
    $check(
      'Index populated',
      $hasData,
      $hasData
        ? "{$stats['chunks']} chunks, {$stats['embedded']} embedded"
        : "no data — run: python3 ingestion/run_pipeline.py --crawl --embed"
    );

    // 5. Manifest file
    $manifestPath = $config->get('manifest_path') ?? '';
    if (!empty($manifestPath)) {
      $manifestOk = file_exists($manifestPath) && is_readable($manifestPath);
      $check('Manifest file readable', $manifestOk, $manifestOk ? $manifestPath : "not found at {$manifestPath}");
    }
    else {
      $this->output()->writeln('  [-] Manifest path not configured (optional — set in admin UI)');
    }

    // 6. Azure/OpenAI connectivity (live test)
    if ($keySet && $baseOk) {
      $this->output()->writeln('  [~] Testing API connectivity...');
      $connectOk = $this->testApiConnectivity($config);
      $check('API connectivity (live ping)', $connectOk, $connectOk ? 'embedding call succeeded' : 'API call failed — check key, URL, and network');
    }
    else {
      $this->output()->writeln('  [-] API connectivity skipped (key or URL not configured)');
    }

    $this->output()->writeln('');
    $this->output()->writeln("Passed: {$passed}  Failed: {$failed}");

    if ($failed > 0) {
      throw new \RuntimeException("Health check failed ({$failed} issue(s)).");
    }
  }

  /**
   * Run a minimal embedding call to verify API connectivity.
   *
   * Uses the configured client settings. Returns true on success.
   */
  protected function testApiConnectivity($config): bool {
    $apiBase    = rtrim($config->get('openai_api_base') ?? '', '/');
    $provider   = $config->get('provider') ?? 'openai';
    $model      = $config->get('embedding_model') ?? 'text-embedding-3-small';
    $apiVersion = $config->get('openai_api_version') ?? '';
    $apiKey     = getenv('DCPAS_OPENAI_API_KEY') ?: ($config->get('openai_api_key') ?? '');

    if ($provider === 'azure') {
      $version = $apiVersion ?: '2024-02-01';
      $url     = "{$apiBase}/deployments/{$model}/embeddings?api-version={$version}";
    }
    else {
      $url = "{$apiBase}/embeddings";
    }

    $headers = ['Content-Type: application/json'];
    if ($provider === 'azure') {
      $headers[] = "api-key: {$apiKey}";
    }
    else {
      $headers[] = "Authorization: Bearer {$apiKey}";
    }

    $payload = json_encode(['input' => 'healthcheck', 'model' => $model]);

    $ch = curl_init($url);
    curl_setopt_array($ch, [
      CURLOPT_POST           => TRUE,
      CURLOPT_POSTFIELDS     => $payload,
      CURLOPT_HTTPHEADER     => $headers,
      CURLOPT_RETURNTRANSFER => TRUE,
      CURLOPT_TIMEOUT        => 10,
      CURLOPT_SSL_VERIFYPEER => TRUE,
    ]);
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($response === FALSE || $httpCode !== 200) {
      return FALSE;
    }
    $data = json_decode($response, TRUE);
    return !empty($data['data'][0]['embedding']);
  }

}
