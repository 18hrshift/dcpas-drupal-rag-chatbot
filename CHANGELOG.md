# Changelog

All notable changes to the DCPAS RAG Chatbot are documented here.

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
