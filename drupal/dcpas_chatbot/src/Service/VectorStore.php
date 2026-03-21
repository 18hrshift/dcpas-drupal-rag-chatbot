<?php

namespace Drupal\dcpas_chatbot\Service;

/**
 * Backward-compatibility alias for SqliteVectorStore.
 *
 * @deprecated Use SqliteVectorStore directly, or — better — type-hint against
 *   VectorStoreInterface and receive dcpas_chatbot.vector_store from the
 *   container (which is VectorStoreLocator). This class will be removed in
 *   a future major version.
 *
 * Sprint 8: the active vector store service (dcpas_chatbot.vector_store) is
 * now VectorStoreLocator, not this class. New code must not reference VectorStore
 * directly.
 */
class VectorStore extends SqliteVectorStore {}
