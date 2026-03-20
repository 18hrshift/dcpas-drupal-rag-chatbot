<?php

namespace Drupal\dcpas_chatbot\Plugin\Block;

use Drupal\Core\Block\BlockBase;
use Drupal\Core\Block\BlockPluginInterface;
use Drupal\Core\Config\ConfigFactoryInterface;
use Drupal\Core\Plugin\ContainerFactoryPluginInterface;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Provides the DCPAS Chatbot block.
 *
 * @Block(
 *   id = "dcpas_chatbot_block",
 *   admin_label = @Translation("DCPAS Chatbot"),
 *   category = @Translation("DCPAS")
 * )
 */
class ChatbotBlock extends BlockBase implements BlockPluginInterface, ContainerFactoryPluginInterface {

  public function __construct(
    array $configuration,
    string $plugin_id,
    mixed $plugin_definition,
    protected readonly ConfigFactoryInterface $configFactory,
  ) {
    parent::__construct($configuration, $plugin_id, $plugin_definition);
  }

  /**
   * {@inheritdoc}
   */
  public static function create(ContainerInterface $container, array $configuration, $plugin_id, $plugin_definition): static {
    return new static(
      $configuration,
      $plugin_id,
      $plugin_definition,
      $container->get('config.factory'),
    );
  }

  /**
   * {@inheritdoc}
   */
  public function build(): array {
    $config = $this->configFactory->get('dcpas_chatbot.settings');

    if (!$config->get('enabled')) {
      return [];
    }

    // Generate a CSRF token for the chat endpoint.
    $csrfToken = \Drupal::csrfToken()->get('dcpas_chatbot_chat');

    return [
      '#theme'    => 'dcpas_chatbot_block',
      '#title'    => $config->get('chatbot_title') ?: 'DCPAS Assistant',
      '#placeholder' => $config->get('placeholder_text') ?: 'Ask a question...',
      '#attached' => [
        'library'       => ['dcpas_chatbot/chatbot'],
        'drupalSettings' => [
          'dcpasChatbot' => [
            'endpoint'   => '/api/dcpas-chatbot/chat',
            'csrfToken'  => $csrfToken,
          ],
        ],
      ],
      '#cache' => [
        // Vary by session so the CSRF token is always fresh.
        'contexts' => ['session'],
        'max-age'  => 0,
      ],
    ];
  }

}
