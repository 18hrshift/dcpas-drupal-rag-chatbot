# TOOLBOX.md — DCPAS RAG Chatbot Operations Reference

> Command reference for developers and operators. Updated every sprint.
> Last updated: Sprint 7.

---

## Ingestion Pipeline

### Prerequisites
```bash
cp .env.example .env
# For standard OpenAI (demo): set OPENAI_API_KEY, EMBEDDING_MODEL, CHAT_MODEL
# For Azure OpenAI (FedRAMP production): set OPENAI_API_BASE (Azure endpoint),
#   OPENAI_API_VERSION, EMBEDDING_DEPLOYMENT, CHAT_DEPLOYMENT, OPENAI_API_KEY
```

### Run full pipeline
```bash
cd ingestion/
python3 run_pipeline.py
```

### Run individual steps
```bash
python3 crawl.py          # Fetch pages from dcpas.osd.mil → data/crawled/
python3 extract.py        # HTML → clean text → data/extracted/
python3 chunk.py          # Text → retrieval chunks → data/chunks/
python3 embed.py          # Chunks → Azure embeddings → data/embeddings/
python3 store.py          # Write chunks + vectors to data/chatbot.db (SQLite)
```

### Verify retrieval
```bash
python3 retrieve.py "What is DCPAS?" --top-k 5
```

### Evaluate retrieval quality (Sprint 7)
```bash
python3 ingestion/evaluate.py
# Runs all fixtures in tests/eval/fixtures.json, reports top-1/top-3 hit rates.

python3 ingestion/evaluate.py --verbose
# Same, with per-fixture output (question, top result URL, scores).

python3 ingestion/evaluate.py --strict
# Exit 1 if top-1 hit rate < 50%.

python3 ingestion/evaluate.py --fixtures tests/eval/fixtures.json --top-k 3
# Custom fixtures path or top-k value.
```

### Dry run (simulate embed without writing)
```bash
python3 ingestion/run_pipeline.py --dry-run --embed
# Runs extract → chunk → injection scan, reports what would be indexed.
# No writes to the store or manifest.
```

### Verify corpus integrity
```bash
python3 ingestion/run_pipeline.py --verify
# Re-derives SHA-256 for every chunk, compares to stored text_hash.
# Reports mismatches and displays the latest index manifest.
```

### Read the manifest
```bash
cat data/index-manifest.json
# Fields: run_at, total_chunks, embedded_chunks, skipped_poisoned, corpus_hash
```

---

## Drupal Module

### Install
```bash
# Copy module to your Drupal installation
cp -r drupal/dcpas_chatbot /path/to/drupal/web/modules/custom/

# Enable module
drush en dcpas_chatbot -y

# Configure at: /admin/config/dcpas-chatbot/settings
```

### Admin configuration path
`/admin/config/dcpas-chatbot/settings`

Required fields:
- Azure OpenAI endpoint, API key, deployment names, API version
- Enable/disable toggle

---

## Tests

### Python tests
```bash
cd tests/
python3 -m pytest -v
```

### PHP code style
```bash
# Requires: phpcs + drupal/coder
phpcs --standard=Drupal --extensions=php,module,install,yml drupal/dcpas_chatbot/src/
```

### JS lint
```bash
# Requires: eslint
eslint drupal/dcpas_chatbot/js/chatbot.js
```

---

## Makefile Targets

```bash
make ingest        # Full pipeline: crawl + embed
make embed         # Embed only (skip crawl)
make dry-run       # Simulate embed — no writes
make verify        # Corpus hash integrity check
make stats         # Index statistics
make healthcheck   # drush dcpas:healthcheck
make test          # Python test suite
make lint          # phpcs + eslint
make install-hooks # Install pre-commit secrets hook
make eval          # Retrieval evaluation (requires populated index)
```

---

## Drush Healthcheck

```bash
drush dcpas:healthcheck
# Checks: enabled, API key, API base URL, index populated,
#         manifest readable, live API connectivity ping
```

Exit code 0 = all checks passed. Non-zero = fix required.

---

## Secrets & Pre-commit Hook

Install the secrets-leak pre-commit hook (scans staged files for API key patterns):
```bash
make install-hooks
# Installs hooks/pre-commit → .git/hooks/pre-commit
```

See `drupal/dcpas_chatbot/config/README.md` for the full secrets management guide
(Azure Key Vault, settings.php injection, env var precedence).

---

## Performance Logging

Chat requests log timing to the `dcpas_chatbot` channel at `info` level:
```
Chat processed. uid=1 ip=x q_hash=abc chunks=5 total_ms=1842 retrieve_ms=340 azure_ms=1480
```

See `PERFORMANCE.md` for thresholds and how to read the logs.

---

## Git Workflow

### Branch model
```
main          ← production-ready, tagged releases only
develop       ← integration target — all PRs merge here
feature/*     ← new capabilities
fix/*         ← bug fixes and security patches
docs/*        ← documentation-only changes
chore/*       ← tooling, deps, config
```

### Start a new sprint
```bash
git checkout develop
git pull origin develop
git checkout -b feature/sprint-N-description
```

### Release a version
```bash
# After sprint PRs are merged to develop and tested:
git checkout main
git merge --no-ff develop
git tag -a v0.X.0 -m "Release v0.X.0 — Sprint N description"
git push origin main --tags
```

### Tag baseline (v0.3.0 = post Sprint 3)
```bash
git tag -a v0.3.0 -m "Release v0.3.0 — MVP + security hardening baseline"
```

---

## CI (GitHub Actions)

Three jobs run on every push and PR:

| Job | Tool | What it checks |
|-----|------|---------------|
| `python-tests` | pytest | All tests in `tests/` |
| `php-codestyle` | phpcs + Drupal coding standards | `src/` PHP files |
| `js-lint` | eslint | `chatbot.js` |

Workflow file: `.github/workflows/ci.yml`

---

## Environment Variables

See `.env.example` for all supported variables. The pipeline uses standard names for both providers:

| Variable | Used for | Example |
|----------|----------|---------|
| `OPENAI_API_KEY` | Both | `sk-...` (standard) or Azure key |
| `OPENAI_API_BASE` | Azure only | `https://{resource}.openai.azure.com/openai` |
| `OPENAI_API_VERSION` | Azure only | `2024-02-01` |
| `EMBEDDING_MODEL` | Standard OpenAI | `text-embedding-3-small` |
| `CHAT_MODEL` | Standard OpenAI | `gpt-4o` |
| `EMBEDDING_DEPLOYMENT` | Azure only | your deployment name |
| `CHAT_DEPLOYMENT` | Azure only | your deployment name |
| `TARGET_URL` | Crawler | `https://dcpas.osd.mil` |
| `MAX_PAGES` | Crawler | `500` |
| `CRAWL_DELAY` | Crawler | `1.5` |
| `DB_PATH` | Storage | `data/index.sqlite` |

Azure mode activates automatically when `OPENAI_API_VERSION` is set or `OPENAI_API_BASE` contains `azure.com`.
