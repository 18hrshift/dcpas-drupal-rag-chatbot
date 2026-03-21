<?php

namespace Drupal\dcpas_chatbot\Form;

use Drupal\Core\Config\ConfigFactoryInterface;
use Drupal\Core\Form\ConfigFormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\dcpas_chatbot\Service\VectorStore;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Admin settings form for the DCPAS Chatbot.
 *
 * Route: /admin/config/dcpas-chatbot/settings
 * Permission: administer dcpas chatbot
 *
 * API key handling:
 *  - Stored in Drupal config as a fallback only.
 *  - If DCPAS_OPENAI_API_KEY environment variable is set on the server,
 *    it takes precedence and the config value is never used.
 *  - For production FedRAMP deployments, use the environment variable and
 *    leave the config field blank. This keeps secrets out of the database
 *    and config exports.
 */
class SettingsForm extends ConfigFormBase {

  protected VectorStore $vectorStore;

  public function __construct(ConfigFactoryInterface $configFactory) {
    parent::__construct($configFactory);
  }

  /**
   * {@inheritdoc}
   */
  public static function create(ContainerInterface $container): static {
    $instance = parent::create($container);
    $instance->vectorStore = $container->get('dcpas_chatbot.vector_store');
    return $instance;
  }

  /**
   * {@inheritdoc}
   */
  protected function getEditableConfigNames(): array {
    return ['dcpas_chatbot.settings'];
  }

  /**
   * {@inheritdoc}
   */
  public function getFormId(): string {
    return 'dcpas_chatbot_settings_form';
  }

  /**
   * {@inheritdoc}
   */
  public function buildForm(array $form, FormStateInterface $form_state): array {
    $config   = $this->config('dcpas_chatbot.settings');
    $stats    = $this->vectorStore->getStats();
    $version  = $this->vectorStore->getLatestIndexVersion();
    $manifest = $this->vectorStore->getManifest();

    $envKeySet = !empty(getenv('DCPAS_OPENAI_API_KEY'));

    // --- Status ---
    $form['status'] = [
      '#type'  => 'details',
      '#title' => $this->t('Index Status'),
      '#open'  => TRUE,
    ];
    $form['status']['info'] = [
      '#markup' => $this->t(
        '<p><strong>Chunks:</strong> @chunks &nbsp; <strong>Embedded:</strong> @emb &nbsp; <strong>Index version:</strong> @ver</p>',
        ['@chunks' => $stats['chunks'], '@emb' => $stats['embedded'], '@ver' => $version]
      ),
    ];

    if ($manifest !== NULL) {
      $poisoned = (int) ($manifest['skipped_poisoned'] ?? 0);
      $poisonedText = $poisoned > 0
        ? '<strong style="color:red"> ⚠ ' . $poisoned . ' skipped (injection pattern)</strong>'
        : ' (none skipped)';
      $form['status']['manifest'] = [
        '#markup' => $this->t(
          '<p><strong>Last ingest run:</strong> @run &nbsp; '
          . '<strong>Total chunks:</strong> @total &nbsp; '
          . '<strong>Skipped/poisoned:</strong>@poisoned</p>'
          . '<p><strong>Corpus hash:</strong> <code>@hash</code></p>',
          [
            '@run'      => $manifest['run_at'] ?? 'unknown',
            '@total'    => $manifest['total_chunks'] ?? '?',
            '@poisoned' => $poisonedText,
            '@hash'     => $manifest['corpus_hash'] ?? 'unknown',
          ]
        ),
      ];
    }

    // --- Global on/off ---
    $form['enabled'] = [
      '#type'          => 'checkbox',
      '#title'         => $this->t('Enable chatbot'),
      '#default_value' => $config->get('enabled'),
    ];

    // --- API Settings ---
    $form['api'] = [
      '#type'  => 'details',
      '#title' => $this->t('API Settings'),
      '#open'  => TRUE,
    ];

    if ($envKeySet) {
      $form['api']['env_key_notice'] = [
        '#markup' => '<p><strong>' . $this->t('API key is set via the DCPAS_OPENAI_API_KEY environment variable. The field below is ignored.') . '</strong></p>',
      ];
    }
    else {
      $form['api']['env_key_hint'] = [
        '#markup' => '<p>' . $this->t('For production/FedRAMP deployments, set the <code>DCPAS_OPENAI_API_KEY</code> environment variable on the server instead of storing the key here. The env var takes precedence.') . '</p>',
      ];
    }

    $form['api']['openai_api_key'] = [
      '#type'          => 'password',
      '#title'         => $this->t('API Key (fallback — prefer env var in production)'),
      '#description'   => $this->t('Leave blank to keep the existing value.'),
      '#default_value' => '',
      '#disabled'      => $envKeySet,
      '#attributes'    => ['autocomplete' => 'off'],
    ];
    $form['api']['provider'] = [
      '#type'          => 'select',
      '#title'         => $this->t('Provider'),
      '#options'       => ['openai' => 'Standard OpenAI', 'azure' => 'Azure OpenAI'],
      '#default_value' => $config->get('provider') ?? 'openai',
      '#description'   => $this->t('Select Azure OpenAI for FedRAMP production deployments.'),
    ];
    $form['api']['openai_api_base'] = [
      '#type'          => 'textfield',
      '#title'         => $this->t('API Base URL'),
      '#description'   => $this->t('OpenAI: <code>https://api.openai.com/v1</code>. Azure: <code>https://{resource}.openai.azure.com/openai</code>'),
      '#default_value' => $config->get('openai_api_base'),
    ];
    $form['api']['openai_api_version'] = [
      '#type'          => 'textfield',
      '#title'         => $this->t('Azure API Version'),
      '#description'   => $this->t('Azure only (e.g. <code>2024-02-01</code>). Leave blank for standard OpenAI.'),
      '#default_value' => $config->get('openai_api_version'),
    ];
    $form['api']['api_timeout'] = [
      '#type'          => 'number',
      '#title'         => $this->t('API request timeout (seconds)'),
      '#description'   => $this->t('Max seconds to wait for a response. Recommended: 10–15 for interactive chat.'),
      '#default_value' => $config->get('api_timeout') ?? 15,
      '#min'           => 5,
      '#max'           => 60,
    ];

    // --- Models ---
    $form['models'] = [
      '#type'  => 'details',
      '#title' => $this->t('Model / Deployment Names'),
      '#open'  => TRUE,
    ];
    $form['models']['embedding_model'] = [
      '#type'          => 'textfield',
      '#title'         => $this->t('Embedding model'),
      '#description'   => $this->t('Standard OpenAI: <code>text-embedding-3-small</code>. Azure: your deployment name.'),
      '#default_value' => $config->get('embedding_model'),
    ];
    $form['models']['chat_model'] = [
      '#type'          => 'textfield',
      '#title'         => $this->t('Chat model'),
      '#description'   => $this->t('Standard OpenAI: <code>gpt-4o</code>. Azure: your deployment name.'),
      '#default_value' => $config->get('chat_model'),
    ];

    // --- Retrieval ---
    $form['retrieval'] = [
      '#type'  => 'details',
      '#title' => $this->t('Retrieval Settings'),
    ];
    $form['retrieval']['top_k'] = [
      '#type'          => 'number',
      '#title'         => $this->t('Top-K chunks'),
      '#description'   => $this->t('How many context chunks to retrieve per question (3–10 recommended).'),
      '#default_value' => $config->get('top_k') ?? 5,
      '#min'           => 1,
      '#max'           => 20,
    ];
    $form['retrieval']['min_score'] = [
      '#type'          => 'number',
      '#title'         => $this->t('Minimum similarity score'),
      '#description'   => $this->t('Chunks below this cosine similarity threshold are discarded. Range 0–1. Default 0.70. Lower = more results but less relevant.'),
      '#default_value' => $config->get('min_score') ?? 0.70,
      '#min'           => 0.0,
      '#max'           => 1.0,
      '#step'          => 0.05,
    ];
    $form['retrieval']['max_response_tokens'] = [
      '#type'          => 'number',
      '#title'         => $this->t('Max response tokens'),
      '#default_value' => $config->get('max_response_tokens') ?? 800,
      '#min'           => 100,
      '#max'           => 4000,
    ];
    $form['retrieval']['max_chunks'] = [
      '#type'          => 'number',
      '#title'         => $this->t('Max corpus chunks to load'),
      '#description'   => $this->t(
        'Maximum chunks loaded into PHP memory for cosine similarity search. '
        . 'Lower values reduce memory usage. Recommended: 10 000 for production, 50 000 for dev. '
        . 'Hard ceiling is 50 000 regardless of this value. See CLAUDE.md § Memory Safety.'
      ),
      '#default_value' => $config->get('max_chunks') ?? 10000,
      '#min'           => 100,
      '#max'           => 50000,
    ];
    $form['retrieval']['manifest_path'] = [
      '#type'          => 'textfield',
      '#title'         => $this->t('Index manifest path (filesystem)'),
      '#description'   => $this->t(
        'Absolute path to the <code>index-manifest.json</code> file written by the ingestion pipeline. '
        . 'Used to display corpus hash and skipped-chunk counts on this page. '
        . 'Example: <code>/var/www/dcpas-rag/data/index-manifest.json</code>. '
        . 'Leave blank to hide the manifest section.'
      ),
      '#default_value' => $config->get('manifest_path') ?? '',
    ];

    // --- Rate limiting ---
    $form['rate'] = [
      '#type'  => 'details',
      '#title' => $this->t('Rate Limiting'),
    ];
    $form['rate']['rate_limit_window'] = [
      '#type'          => 'number',
      '#title'         => $this->t('Window (seconds)'),
      '#default_value' => $config->get('rate_limit_window') ?? 60,
      '#min'           => 10,
    ];
    $form['rate']['rate_limit_max'] = [
      '#type'          => 'number',
      '#title'         => $this->t('Max requests per window'),
      '#default_value' => $config->get('rate_limit_max') ?? 10,
      '#min'           => 1,
    ];

    // --- Widget text ---
    $form['ui'] = [
      '#type'  => 'details',
      '#title' => $this->t('Widget Text'),
    ];
    $form['ui']['chatbot_title'] = [
      '#type'          => 'textfield',
      '#title'         => $this->t('Widget title'),
      '#default_value' => $config->get('chatbot_title'),
      '#maxlength'     => 100,
    ];
    $form['ui']['placeholder_text'] = [
      '#type'          => 'textfield',
      '#title'         => $this->t('Input placeholder'),
      '#default_value' => $config->get('placeholder_text'),
      '#maxlength'     => 200,
    ];
    $form['ui']['system_prompt'] = [
      '#type'          => 'textarea',
      '#title'         => $this->t('System prompt'),
      '#description'   => $this->t('Instructions sent to the model before every chat request. Changes take effect immediately. Max 2 000 characters.'),
      '#rows'          => 6,
      '#default_value' => $config->get('system_prompt'),
      '#maxlength'     => 2000,
    ];

    return parent::buildForm($form, $form_state);
  }

  /**
   * {@inheritdoc}
   */
  public function validateForm(array &$form, FormStateInterface $form_state): void {
    $base = trim($form_state->getValue('openai_api_base'));
    if (!empty($base) && !str_starts_with($base, 'https://')) {
      $form_state->setErrorByName('openai_api_base', $this->t('API base URL must start with https://.'));
    }

    $prompt = $form_state->getValue('system_prompt');
    if (mb_strlen($prompt) > 2000) {
      $form_state->setErrorByName('system_prompt', $this->t('System prompt must be 2 000 characters or fewer.'));
    }

    parent::validateForm($form, $form_state);
  }

  /**
   * {@inheritdoc}
   */
  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $config = $this->config('dcpas_chatbot.settings');

    $config
      ->set('enabled', (bool) $form_state->getValue('enabled'))
      ->set('provider', $form_state->getValue('provider'))
      ->set('openai_api_base', trim($form_state->getValue('openai_api_base')))
      ->set('openai_api_version', trim($form_state->getValue('openai_api_version')))
      ->set('embedding_model', trim($form_state->getValue('embedding_model')))
      ->set('chat_model', trim($form_state->getValue('chat_model')))
      ->set('top_k', (int) $form_state->getValue('top_k'))
      ->set('min_score', (float) $form_state->getValue('min_score'))
      ->set('max_response_tokens', (int) $form_state->getValue('max_response_tokens'))
      ->set('max_chunks', (int) $form_state->getValue('max_chunks'))
      ->set('manifest_path', trim($form_state->getValue('manifest_path')))
      ->set('api_timeout', (int) $form_state->getValue('api_timeout'))
      ->set('rate_limit_window', (int) $form_state->getValue('rate_limit_window'))
      ->set('rate_limit_max', (int) $form_state->getValue('rate_limit_max'))
      ->set('chatbot_title', $form_state->getValue('chatbot_title'))
      ->set('placeholder_text', $form_state->getValue('placeholder_text'))
      ->set('system_prompt', $form_state->getValue('system_prompt'));

    // Only update the API key if a new one was explicitly provided.
    // Blank password field = keep the existing value.
    $newKey = $form_state->getValue('openai_api_key');
    if (!empty($newKey) && empty(getenv('DCPAS_OPENAI_API_KEY'))) {
      $config->set('openai_api_key', $newKey);
    }

    $config->save();
    parent::submitForm($form, $form_state);
  }

}
