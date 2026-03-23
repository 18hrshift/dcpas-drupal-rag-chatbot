# DCPAS RAG Chatbot

A Retrieval-Augmented Generation (RAG) chatbot for Drupal 10, built for unclassified U.S. government environments. Crawls a target site, embeds its content into a vector index, and answers user questions grounded in that corpus — with multi-layer security, audit logging, and a FedRAMP-aligned deployment path.

**Status:** Production-ready (v1.0.0) · **Target:** dcpas.osd.mil or any unclassified Drupal 10 site

---

## Architecture Overview

```
[Ingestion Pipeline]          [Drupal Module]
  crawler.py                    ChatController.php  ← AJAX POST handler
  extractor.py                  Retriever.php       ← orchestrates lookup
  chunker.py          ──────►   VectorStoreLocator  ← SQLite or pgvector
  embedder.py        index       AzureOpenAIClient  ← completions
  store.py                      PromptBuilder.php   ← RAG prompt + citations
```

The ingestion pipeline is Python stdlib-only (no third-party packages — FedRAMP environments have strict package approval requirements). The Drupal module is a standard Drupal 10 module with 10 services.

**Vector store backends:**
- `SqliteVectorStore` — default, no extra infra, handles up to ~50K chunks
- `PgVectorStore` — PostgreSQL pgvector, for large corpora (see `PERFORMANCE.md`)

---

## Repository Layout

```
drupal/dcpas_chatbot/      Drupal 10 module (PHP)
ingestion/                 Ingestion pipeline (Python, stdlib-only)
tests/                     Python unit tests (47 tests)
tests/eval/fixtures.json   22 Q&A pairs for retrieval evaluation
hooks/pre-commit           Secrets-leak prevention hook
.env.example               Environment variable template
Makefile                   Common dev tasks (make test, make ingest, …)
```

**Key docs:**

| File | Contents |
|------|----------|
| `CLAUDE.md` | Architecture decisions, service boundaries, security design |
| `DEPLOY.md` | Step-by-step deployment guide |
| `DEMO.md` | Quick-start for the demo environment (dvapp21) |
| `SECURITY.md` | Threat model, prompt injection defence, audit logging |
| `TOOLBOX.md` | Operations: health checks, troubleshooting, corpus verification |
| `PERFORMANCE.md` | When and how to migrate to pgvector |
| `CHANGELOG.md` | Version history (v0.3.0 → v1.0.0) |
| `ROADMAP.md` | Sprint history and production roadmap |

---

## Quick Start

**Requirements:** Python 3.9+, PHP 8.1+, Drupal 10, Azure OpenAI (or standard OpenAI) credentials.

```bash
# 1. Configure environment
cp .env.example .env
# Fill in OPENAI_API_KEY (or Azure equivalents), TARGET_URL, DB_PATH

# 2. Run ingestion pipeline
make ingest          # crawl → extract → chunk → embed → store
make test            # run 47 unit tests
make eval            # retrieval evaluation against fixtures

# 3. Install the Drupal module
cp -r drupal/dcpas_chatbot /path/to/drupal/web/modules/custom/
drush en dcpas_chatbot
drush cr

# 4. Configure via Drupal admin
# Admin → Configuration → DCPAS Chatbot Settings
# Set API key, system prompt, rate limits, vector store backend
```

See `DEPLOY.md` for the full deployment checklist and `DEMO.md` for the demo environment specifics.

---

## Security

Ten-stage request pipeline: CSRF → flood control → input normalization → homoglyph normalization → prompt injection blocklist → retrieval → RAG prompt (XML-tagged corpus boundary) → Azure call → audit log → sanitized response.

Audit log records `sha256(question)` — never plaintext. See `SECURITY.md` for the full threat model.

---

## Development

```bash
make test       # Python unit tests
make lint       # phpcs (Drupal standard) + Python flake8
make healthcheck  # drush dcpas:healthcheck
make eval       # retrieval evaluation
```

Git workflow: `develop` is the integration branch. PRs merge to `develop`, tagged releases go to `main`. See `CONTRIBUTING.md`.
