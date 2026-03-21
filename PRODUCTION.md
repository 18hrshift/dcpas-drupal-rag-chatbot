# PRODUCTION.md — Migration from Demo to FedRAMP Production

> This document covers what changes when moving from the demo setup
> (ingestion on OpenClaw VM + standard OpenAI) to a production FedRAMP
> deployment (ingestion inside the boundary + Azure OpenAI).

---

## Demo vs Production Architecture

| Concern | Demo (dvapp21) | Production (FedRAMP) |
|---------|---------------|----------------------|
| Ingestion runs on | OpenClaw VM (outside boundary) | Server inside FedRAMP boundary |
| API provider | Standard OpenAI (`api.openai.com`) | Azure OpenAI (FedRAMP High authorized) |
| Corpus transport | SQLite → SQL dump → scp → MySQL import | Python writes directly to MySQL (no export step) |
| API key storage | settings.php or env var on dev server | Azure Key Vault → env var (see `config/README.md`) |
| PHP intl extension | Missing (normalization skipped) | Must be installed |
| Python version | 3.6.8 on server (irrelevant — runs on VM) | 3.9+ on the server inside the boundary |

**The demo setup is acceptable because dcpas.osd.mil is a public website
with no CUI, PII, or sensitive data.** Sending public content to standard
OpenAI from a dev VM carries no FedRAMP risk for the demo phase.

---

## What Changes for Production

### 1. Move Ingestion Inside the FedRAMP Boundary

The ingestion pipeline must run on a FedRAMP-authorized compute resource —
the Drupal server itself, or a dedicated worker VM inside the boundary.

```
FedRAMP boundary
┌──────────────────────────────────────────────────┐
│                                                  │
│  Worker (Drupal server or dedicated Azure VM)    │
│    python3 ingestion/run_pipeline.py             │
│         │                                        │
│         ▼                                        │
│    Azure OpenAI (FedRAMP High authorized)        │
│         │                                        │
│         ▼                                        │
│    MySQL / PostgreSQL (same private network)     │
│                                                  │
└──────────────────────────────────────────────────┘
```

The `export_mysql.py` / `scp` / SQL import steps go away entirely. Python
writes directly to the database.

### 2. Switch to Azure OpenAI

Set these environment variables on the production server:

```bash
OPENAI_API_KEY=<Azure key from Key Vault>
OPENAI_API_BASE=https://{resource}.openai.azure.com/openai
OPENAI_API_VERSION=2024-02-01
EMBEDDING_DEPLOYMENT=<your embedding deployment name>
CHAT_DEPLOYMENT=<your GPT-4 deployment name>
```

Azure mode activates automatically when `OPENAI_API_VERSION` is set.
No code changes — the pipeline already supports both providers.

Also update Drupal admin settings:

| Field | Value |
|-------|-------|
| Provider | Azure OpenAI |
| API Base URL | `https://{resource}.openai.azure.com/openai` |
| Azure API Version | `2024-02-01` |
| Embedding model | your embedding deployment name |
| Chat model | your GPT-4 deployment name |
| API Key | via `DCPAS_OPENAI_API_KEY` env var (Key Vault reference) |

### 3. Install PHP intl Extension

Required for Unicode homoglyph normalization (injection defence):

```bash
# RHEL/CentOS:
sudo yum install php-intl

# Debian/Ubuntu:
sudo apt install php8.1-intl

# Restart php-fpm after installing
```

### 4. Secure the API Key with Azure Key Vault

See `drupal/dcpas_chatbot/config/README.md § Azure Key Vault` for the
full setup. Summary:

1. Store the Azure OpenAI key in Key Vault as a secret.
2. Grant the app service identity `Key Vault Secrets User` role.
3. Map the Key Vault reference to `DCPAS_OPENAI_API_KEY` env var.
4. Remove `openai_api_key` from settings.php and the Drupal config DB.

### 5. Schedule Regular Re-ingestion

dcpas.osd.mil content changes over time. Set up a cron job on the
production worker to re-run the pipeline on a regular schedule:

```bash
# Example: re-ingest every Sunday at 2am
0 2 * * 0 cd /opt/dcpas-rag && python3 ingestion/run_pipeline.py \
  >> /var/log/dcpas-ingest.log 2>&1
```

After each run, run the healthcheck to verify the updated corpus:

```bash
drush dcpas:healthcheck
```

### 6. Consider pgvector at Scale

If the corpus grows beyond ~50,000 chunks or query latency degrades,
migrate to pgvector. See `DEPLOY.md § pgvector Setup`.

The trigger thresholds are documented in `PERFORMANCE.md`.

---

## Production Checklist

Before go-live:

- [ ] Ingestion pipeline running inside the FedRAMP boundary
- [ ] Azure OpenAI endpoint configured and tested (`drush dcpas:healthcheck`)
- [ ] `php-intl` extension installed and verified (`php -m | grep intl`)
- [ ] API key stored in Azure Key Vault, not in settings.php or config DB
- [ ] `DCPAS_OPENAI_API_KEY` env var set on the server, not in code
- [ ] Re-ingestion cron job scheduled and tested
- [ ] `make verify` passes (corpus hash integrity check)
- [ ] `drush dcpas:healthcheck` exits 0
- [ ] `export_mysql.py` and VM-based workflow removed from runbooks
- [ ] WCAG contrast audit completed (see `CLAUDE.md § WCAG`)
- [ ] Screen reader test (NVDA or JAWS) completed
- [ ] Rate limits reviewed for expected production traffic
- [ ] `min_score` threshold validated against real query traffic

---

## Files That Change Between Demo and Production

| File | Demo value | Production value |
|------|-----------|-----------------|
| `.env` (on VM) | `OPENAI_API_KEY=sk-...` | Not used (runs on server inside boundary) |
| `settings.php` | `$config[...]['openai_api_key'] = 'sk-...'` | Remove — use env var from Key Vault |
| Admin: Provider | Standard OpenAI | Azure OpenAI |
| Admin: API Base URL | `https://api.openai.com/v1` | `https://{resource}.openai.azure.com/openai` |
| Admin: API Version | *(blank)* | `2024-02-01` |
| Admin: Embedding model | `text-embedding-3-small` | Azure deployment name |
| Admin: Chat model | `gpt-4o` | Azure deployment name |

**No code changes required.** All of this is configuration.
