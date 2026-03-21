# TOOLBOX.md — DCPAS RAG Chatbot Operations Reference

> Command reference for developers and operators. Updated every sprint.
> Last updated: Sprint 4.

---

## Ingestion Pipeline

### Prerequisites
```bash
cp .env.example .env
# Edit .env — set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY,
#              AZURE_OPENAI_EMBEDDING_DEPLOYMENT
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

See `.env.example` for all supported variables. Key ones:

| Variable | Purpose |
|----------|---------|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI resource endpoint |
| `AZURE_OPENAI_API_KEY` | API key for Azure OpenAI |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | Embedding model deployment name |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | GPT-4 deployment name |
| `AZURE_OPENAI_API_VERSION` | API version (e.g. `2024-02-01`) |
