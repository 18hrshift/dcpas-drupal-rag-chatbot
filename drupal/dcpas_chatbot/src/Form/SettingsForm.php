<?php

namespace Drupal\dcpas_chatbot\Form;

use Drupal\Core\Form\ConfigFormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\dcpas_chatbot\Service\VectorStore;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Admin settings form for the DCPAS Chatbot.
 *
 * Route: /admin/config/dcpas-chatbot/settings
 * Permission: administer dcpas chatbot
 */
class SettingsForm extends ConfigFormBase {

  public function __construct(
    protected readonly VectorStore $vectorStore,
  ) {}

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
    $config = $this->config('dcpas_chatbot.settings');
    $stats  = [];
    try {
      $stats = $this->vectorStore->getStats();
      $version = $this->vectorStore->getLatestIndexVersion();
    }
    catch (\Exception $e) {
      $version = 'unavailable (tables not yet created)';
    }

    // --- Status ---
    $form['status'] = [
      '#type'  => 'details',
      '#title' => $this->t('Index Status'),
      '#open'  => TRUE,
    ];
    $form['status']['info'] = [
      '#markup' => $this->t(
        '<p><strong>Chunks:</strong> @chunks &nbsp; <strong>Embedded:</strong> @emb &nbsp; <strong>Index version:</strong> @ver</p>',
        [
          '@chunks' => $stats['chunks'] ?? '—',
          '@emb'    => $stats['embedded'] ?? '—',
          '@ver'    => $version,
        ]
      ),
    ];

    // --- Chatbot on/off ---
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
    $form['api']['openai_api_key'] = [
      '#type'          => 'password',
      '#title'         => $this->t('API Key'),
      '#description'   => $this->t('OpenAI or Azure OpenAI API key. Leave blank to keep the existing value.'),
      '#default_value' => '',
      '#attributes'    => ['autocomplete' => 'off'],
    ];
    $form['api']['openai_api_base'] = [
      '#type'          => 'textfield',
      '#title'         => $this->t('API Base URL'),
      '#description'   => $this->t('Standard OpenAI: <code>https://api.openai.com/v1</code>. Azure: <code>https://{resource}.openai.azure.com/openai</code>'),
      '#default_value' => $config->get('openai_api_base'),
    ];
    $form['api']['openai_api_version'] = [
      '#type'          => 'textfield',
      '#title'         => $this->t('Azure API Version'),
      '#description'   => $this->t('Leave blank for standard OpenAI. Azure example: <code>2024-02-01</code>'),
      '#default_value' => $config->get('openai_api_version'),
    ];

    // --- Models ---
    $form['models'] = [
      '#type'  => 'details',
      '#title' => $this->t('Model / Deployment Settings'),
      '#open'  => TRUE,
    ];
    $form['models']['embedding_model'] = [
      '#type'          => 'textfield',
      '#title'         => $this->t('Embedding Model'),
      '#description'   => $this->t('Standard OpenAI: <code>text-embedding-3-small</code>. Azure: your deployment name.'),
      '#default_value' => $config->get('embedding_model'),
    ];
    $form['models']['chat_model'] = [
      '#type'          => 'textfield',
      '#title'         => $this->t('Chat Model'),
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
    $form['retrieval']['max_response_tokens'] = [
      '#type'          => 'number',
      '#title'         => $this->t('Max response tokens'),
      '#default_value' => $config->get('max_response_tokens') ?? 800,
      '#min'           => 100,
      '#max'           => 4000,
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

    // --- UI ---
    $form['ui'] = [
      '#type'  => 'details',
      '#title' => $this->t('Widget Text'),
    ];
    $form['ui']['chatbot_title'] = [
      '#type'          => 'textfield',
      '#title'         => $this->t('Widget title'),
      '#default_value' => $config->get('chatbot_title'),
    ];
    $form['ui']['placeholder_text'] = [
      '#type'          => 'textfield',
      '#title'         => $this->t('Input placeholder'),
      '#default_value' => $config->get('placeholder_text'),
    ];
    $form['ui']['system_prompt'] = [
      '#type'          => 'textarea',
      '#title'         => $this->t('System prompt'),
      '#rows'          => 6,
      '#default_value' => $config->get('system_prompt'),
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
    parent::validateForm($form, $form_state);
  }

  /**
   * {@inheritdoc}
   */
  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $config = $this->config('dcpas_chatbot.settings');

    $config
      ->set('enabled', (bool) $form_state->getValue('enabled'))
      ->set('openai_api_base', trim($form_state->getValue('openai_api_base')))
      ->set('openai_api_version', trim($form_state->getValue('openai_api_version')))
      ->set('embedding_model', trim($form_state->getValue('embedding_model')))
      ->set('chat_model', trim($form_state->getValue('chat_model')))
      ->set('top_k', (int) $form_state->getValue('top_k'))
      ->set('max_response_tokens', (int) $form_state->getValue('max_response_tokens'))
      ->set('rate_limit_window', (int) $form_state->getValue('rate_limit_window'))
      ->set('rate_limit_max', (int) $form_state->getValue('rate_limit_max'))
      ->set('chatbot_title', $form_state->getValue('chatbot_title'))
      ->set('placeholder_text', $form_state->getValue('placeholder_text'))
      ->set('system_prompt', $form_state->getValue('system_prompt'));

    // Only update API key if a new one was provided (password field blanked = keep existing)
    $newKey = $form_state->getValue('openai_api_key');
    if (!empty($newKey)) {
      $config->set('openai_api_key', $newKey);
    }

    $config->save();
    parent::submitForm($form, $form_state);
  }

}
