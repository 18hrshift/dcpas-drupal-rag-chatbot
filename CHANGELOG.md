# Changelog

All notable changes to the DCPAS RAG Chatbot are documented here.

---

## [v1.0.0] — Sprint 8: pgvector Migration Path

### Added
- `VectorStoreInterface` — contract for all vector store backends (`findSimilar`, `getStats`, `getManifest`, `getLatestIndexVersion`).
- `AbstractVectorStore` — base class with shared DB/manifest/stats logic used by both backends.
- `SqliteVectorStore` — in-process cosine similarity backend; supersedes `VectorStore`. Contains `loadAllWithEmbeddings()`, `cosineSimilarity()`, and all memory safety constants.
- `PgVectorStore` — PostgreSQL + pgvector backend. Issues a single `<=>` ANN query per request; no corpus loading into PHP memory.
- `VectorStoreLocator` — routes to the configured backend based on `vector_store_backend` config. Registered as `dcpas_chatbot.vector_store`.
- `ingestion/migrate_to_pgvector.py` — reads SQLite index, upserts chunks + embeddings into pgvector, builds IVFFlat index. Idempotent. `--dry-run` flag supported.
- `hook_update_9801` in `dcpas_chatbot.install` — creates `dcpas_chatbot_pg_embeddings` table (PostgreSQL only) with IVFFlat index.
- Admin settings: **Vector store backend** selector (sqlite / pgvector).
- `DEPLOY.md § pgvector Setup` — prerequisites, step-by-step migration, troubleshooting.
- Makefile `migrate-pg` target.

### Changed
- `Retriever.php`: removed `cosineSimilarity()` method and in-process scoring loop. Now calls `$this->vectorStore->findSimilar($queryVector, $k, $minScore)`. Type-hint changed from `VectorStore` to `VectorStoreInterface`.
- `SettingsForm.php`, `DcpasChatbotCommands.php`: type-hints updated to `VectorStoreInterface`.
- `services.yml`: `dcpas_chatbot.vector_store` now points to `VectorStoreLocator`; added `dcpas_chatbot.sqlite_vector_store` and `dcpas_chatbot.pg_vector_store`.
- `VectorStore.php`: converted to a deprecated BC alias extending `SqliteVectorStore`.
- Config schema: added `vector_store_backend` key.
- Install defaults: `vector_store_backend: sqlite`.
- AGENTS.md, CLAUDE.md, TOOLBOX.md, ROADMAP.md: updated for Sprint 8.

---

## [v0.7.0] — Sprint 7: Evaluation & Confidence Scoring

### Added
- `tests/eval/fixtures.json` — 22 Q&A fixture pairs with expected source URL prefixes for retrieval evaluation.
- `ingestion/evaluate.py` — loads fixtures, runs retrieval, reports top-1/top-3 hit rates and mean top score. `--verbose`, `--strict`, `--top-k`, `--fixtures` flags.
- `Makefile` `eval` target — runs `evaluate.py --verbose` against the live index.
- CI job `retrieval-eval` in `.github/workflows/ci.yml` — optional; activates only when `CI_EVAL_ENABLED=true` repo variable is set and an `dcpas-index` artifact is present.

### Changed
- `ChatController.php`: added `logger->warning()` on the low-confidence path (when `empty($chunks)`) — logs `uid`, `ip`, `q_hash` only. No question text (PII compliance).
- `AGENTS.md`: added `evaluate.py` to ingestion pipeline component map; added Evaluation Ownership section and rule 6.
- `CLAUDE.md`: added Confidence Scoring & Evaluation section with design rationale.
- `TOOLBOX.md`: added eval commands and `make eval` to Makefile targets table.

---

## [v0.6.0] — Sprint 6: Production Deployment Path

### Added
- `DEPLOY.md` — 10-step deployment guide: module install, API key setup, ingest pipeline, health check, smoke test, block placement, troubleshooting table.
- `drush dcpas:healthcheck` (`DcpasChatbotCommands.php`) — checks enabled state, API key, API base URL, index population, manifest file, and live API connectivity. Exit code 1 on failure.
- `Makefile` — targets: `ingest`, `embed`, `dry-run`, `verify`, `stats`, `healthcheck`, `test`, `lint`, `install-hooks`.
- `hooks/pre-commit` — secrets-leak scanner; blocks commits containing OpenAI API keys, API key assignments, or `.env` files. Install via `make install-hooks`.
- `drupal/dcpas_chatbot/config/README.md` — secrets management guide: env var, settings.php injection, Azure Key Vault path, config export warnings.
- `PERFORMANCE.md` — O(n×d) retrieval analysis, acceptable thresholds, pgvector migration triggers, log query examples, baseline table.

### Changed
- `ChatController.php`: performance timing on every request — `total_ms`, `retrieve_ms`, `azure_ms` logged to `dcpas_chatbot` channel at `info` level.
- `chatbot.js`: `aria-busy="true"` on form while awaiting response; Escape key returns focus to input; `lang="en"` attribute on assistant response paragraphs (WCAG 3.1.2).
- `templates/dcpas-chatbot-block.html.twig`: added `lang="en"` to widget container (WCAG 3.1.1).
- `dcpas_chatbot.services.yml`: registered `DcpasChatbotCommands` as a drush command service.
- `CLAUDE.md`: production secrets model, WCAG compliance table, performance logging design.
- `TOOLBOX.md`: Makefile targets, drush healthcheck, pre-commit hook, performance log format.

---

## [v0.5.0] — Sprint 5: Corpus Integrity & Memory Safety

### Added
- `ingestion/corpus_guard.py` — ingest-time injection scanner; mirrors `ChatController` patterns. Poisoned chunks are skipped and logged before writing to the index.
- `store.py`: SHA-256 `text_hash` stored per chunk at write time. `corpus_hash()` and `verify_hashes()` methods for integrity checking.
- `run_pipeline.py`: `--dry-run` flag (simulate without writes) and `--verify` flag (hash integrity check + manifest display).
- Index manifest (`data/index-manifest.json`) written after each ingest: run_at, total_chunks, embedded_chunks, skipped_poisoned, corpus_hash.
- `VectorStore.php` rewrote `loadAllWithEmbeddings()` with batched loading (1 000 rows/batch) and `memory_get_usage()` ceiling guard (80% of memory_limit). Logs warning and returns partial corpus if ceiling is approached.
- `VectorStore::getManifest()` — reads index manifest JSON for admin display.
- Admin settings: `max_chunks` field (default 10 000, hard cap 50 000) and `manifest_path` config. Manifest section shown on settings page.
- `AGENTS.md` created — component ownership map and no-duplication rules.

### Changed
- `store.py` schema: added `text_hash TEXT` column to chunks table.
- `VectorStore.php`: now accepts `config.factory` and `logger.channel.dcpas_chatbot` as dependencies.

### Fixed
- Memory exhaustion risk on large corpora — replaced single bulk query with batched loader.

---

## [v0.4.0] — Sprint 4: Security Remediation & Git Foundation

### Security fixes
- `ChatController.php`: expanded `PROMPT_INJECTION_PATTERNS` with `System:`, `Assistant:`, `Override:`, `Final answer:`, `<EndOfContext>`, `Disregard`, `Ignore all`.
- `ChatController.php`: added Unicode homoglyph normalization (`FORM_KC`) before blocklist matching.
- `VectorStore.php`: added `is_infinite()` / `is_nan()` guard on vector elements.
- `chatbot.js`: replaced `innerHTML` spinner with `document.createElement` loop.
- `chatbot.js`: added `startsWith('https://')` guard on citation URLs before setting `a.href`.
- `ChatController.php`: added `logger->warning()` on 403 (permission), 403 (CSRF), 429 (rate limit), and API error paths.

### Added
- `CONTRIBUTING.md` — branch model, commit format, PR rules.
- `.github/workflows/ci.yml` — pytest, phpcs, eslint on all branches/PRs.
- `.github/PULL_REQUEST_TEMPLATE.md` — What/Why/Security impact checklist.
- `SECURITY.md` — threat model, audit log schema, known limitations.
- `CLAUDE.md` — full architecture reference.
- `TOOLBOX.md` — pipeline commands, git workflow, CI reference.

### Git
- `develop` branch initialized.
- `main` tagged `v0.3.0` (post-Sprint 3 baseline).

---

## [v0.3.0] — Sprints 1–3: MVP + Security Hardening Baseline

### Sprint 3 — MVP Polish, Citations, Rate Limiting
- Source citations in chat responses (title + URL per chunk).
- Drupal Flood API rate limiting (configurable window/max).
- Admin enable/disable toggle.
- Fallback message when retrieval finds no relevant chunks.

### Sprint 2 — Drupal Module Core
- `ChatController.php` — full request validation pipeline (auth, CSRF, flood, injection guard, retrieval, audit log).
- `VectorStore.php`, `Retriever.php`, `PromptBuilder.php`, `AzureOpenAIClient.php` — service layer.
- `SettingsForm.php` — admin config UI (API settings, models, retrieval params, rate limits, widget text).
- `ChatbotBlock` — block plugin, Twig template, vanilla JS frontend.
- Security hardening: CSRF validation, permission checks, URL scheme validation, `strip_tags()`, `textContent` rendering.

### Sprint 1 — Ingestion Pipeline
- `crawler.py` — same-domain HTTP crawler with robots.txt respect.
- `extractor.py` — HTML → clean text (stdlib only, no third-party parsers).
- `chunker.py` — text chunking with stable SHA-based chunk IDs.
- `embedder.py` — Azure OpenAI embeddings endpoint integration.
- `store.py` — SQLite vector store.
- `retrieve.py` — cosine similarity retrieval (dev/smoke-test tool).
- `run_pipeline.py` — orchestrator; resumable pipeline.
- `export_mysql.py` — export SQLite index to Drupal MySQL schema.
- 47 Python tests across 5 test files.
