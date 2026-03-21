# DEMO.md — dvapp21 / dcpas-dev Deployment Guide

> Exact commands for deploying the chatbot to the dcpas-dev environment.
> Ingestion runs on the **OpenClaw VM**. The Drupal module runs on **dvapp21**.

---

## Environment Summary

| Item | Value |
|------|-------|
| Server | dvapp21 |
| Drupal root | `/var/www/html/dcpas-dev/web` |
| Drush | `vendor/bin/drush --root=/var/www/html/dcpas-dev/web` |
| PHP | 8.1.34 |
| PHP intl | NOT installed (normalization skipped — see note below) |
| DB | MySQL — `44063_DCPAS-DEV2` |
| Drupal table prefix | none (empty string) |
| Module machine name | `dcpas_chatbot` |
| Module install path | `web/modules/custom/dcpas_chatbot/` |
| Private files | `/var/www/html/shared/dcpas-dev-private` |
| Provider for demo | Standard OpenAI |

---

## Known Limitation: intl Extension Missing

The PHP `intl` extension is not installed on dvapp21. This means:

- **Unicode homoglyph normalization is skipped** — Cyrillic/Greek lookalike
  characters in user input will not be caught by the injection filter.
- The standard ASCII injection blocklist still runs normally.
- For production (FedRAMP), install `php-intl` before go-live.

---

## Known Limitation: Drupal DB User is Read-Only

The Drupal app database user has `'readonly' => TRUE` in settings.php. That user
**cannot** run the SQL import. Use a writable MySQL admin/root user for Step 5.

---

## Step 1 — Run the Ingestion Pipeline (on the OpenClaw VM)

```bash
cd /home/openclawjb/projects/drupal-rag-chatbot

# Configure API key
cp .env.example .env
# Edit .env:
#   OPENAI_API_KEY=sk-...
#   EMBEDDING_MODEL=text-embedding-3-small
#   CHAT_MODEL=gpt-4o
#   TARGET_URL=https://dcpas.osd.mil
#   MAX_PAGES=500

# Run the full pipeline
python3 ingestion/run_pipeline.py

# Verify integrity
python3 ingestion/run_pipeline.py --verify
```

---

## Step 2 — Export SQLite Index to MySQL SQL Dump (on the OpenClaw VM)

No table prefix needed (confirmed empty).

```bash
cd /home/openclawjb/projects/drupal-rag-chatbot
python3 ingestion/export_mysql.py --out data/export.sql
```

---

## Step 3 — Copy Module and SQL Dump to dvapp21

```bash
# Create the custom modules directory if it doesn't exist
ssh dvapp21 "mkdir -p /var/www/html/dcpas-dev/web/modules/custom"

# Copy the Drupal module
scp -r drupal/dcpas_chatbot/ dvapp21:/var/www/html/dcpas-dev/web/modules/custom/

# Copy the SQL dump
scp data/export.sql dvapp21:/tmp/dcpas_export.sql

# Copy the index manifest (for admin UI display)
scp data/index-manifest.json \
  dvapp21:/var/www/html/shared/dcpas-dev-private/dcpas-index-manifest.json
```

---

## Step 4 — Import the Corpus into MySQL on dvapp21

The Drupal app user is read-only. Use a writable MySQL user (root or admin):

```bash
# On dvapp21 — use a writable MySQL user, NOT the Drupal app user
mysql -h localhost -u root -p 44063_DCPAS-DEV2 < /tmp/dcpas_export.sql
```

---

## Step 5 — Inject the API Key via settings.php

Keep the API key out of the Drupal database. Add to
`/var/www/html/dcpas-dev/web/sites/default/settings.php`:

```php
// DCPAS Chatbot — API key injection (demo: standard OpenAI)
$config['dcpas_chatbot.settings']['openai_api_key'] = 'sk-...';
```

Or set an environment variable (survives config exports):

```bash
# In php-fpm service override or /etc/environment:
DCPAS_OPENAI_API_KEY=sk-...
```

The env var takes precedence over settings.php which takes precedence over
the Drupal admin UI field.

---

## Step 6 — Enable the Module on dvapp21

```bash
cd /var/www/html/dcpas-dev
vendor/bin/drush --root=/var/www/html/dcpas-dev/web en dcpas_chatbot -y
```

---

## Step 7 — Configure the Module

Go to: `/admin/config/dcpas-chatbot/settings`

| Field | Value for demo |
|-------|---------------|
| Enable chatbot | ✓ checked |
| Provider | Standard OpenAI |
| API Key | Leave blank (set via settings.php above) |
| API Base URL | `https://api.openai.com/v1` |
| Azure API Version | *(leave blank)* |
| Embedding model | `text-embedding-3-small` |
| Chat model | `gpt-4o` |
| Vector store backend | `sqlite` (default) |
| Index manifest path | `/var/www/html/shared/dcpas-dev-private/dcpas-index-manifest.json` |

---

## Step 8 — Run Health Check

```bash
cd /var/www/html/dcpas-dev
vendor/bin/drush --root=/var/www/html/dcpas-dev/web dcpas:healthcheck
```

Expected: all checks passed, index populated, API connectivity OK.

If "API base URL not HTTPS" — the API base URL field may be blank; set it to
`https://api.openai.com/v1` in admin settings.

---

## Step 9 — Place the Block

1. Go to `/admin/structure/block`
2. Click **Place block** in the desired region
3. Search for **DCPAS Chatbot**
4. Save

---

## Step 10 — Smoke Test

Visit a page where the block is placed. Ask: *"What is DCPAS?"*

Expected: a response with a citation link to `dcpas.osd.mil`.

---

## Re-ingesting (after crawl updates)

```bash
# On the OpenClaw VM:
python3 ingestion/run_pipeline.py
python3 ingestion/export_mysql.py --out data/export.sql
scp data/export.sql dvapp21:/tmp/dcpas_export.sql

# On dvapp21 — writable MySQL user:
mysql -h localhost -u root -p 44063_DCPAS-DEV2 < /tmp/dcpas_export.sql

# Clear Drupal cache:
cd /var/www/html/dcpas-dev
vendor/bin/drush --root=/var/www/html/dcpas-dev/web cr
```

---

## Switching to Azure OpenAI (production)

When Azure credentials are ready, update admin settings:

| Field | Value |
|-------|-------|
| Provider | Azure OpenAI |
| API Base URL | `https://{resource}.openai.azure.com/openai` |
| Azure API Version | `2024-02-01` |
| Embedding model | your embedding deployment name |
| Chat model | your GPT-4 deployment name |
| API Key | via `DCPAS_OPENAI_API_KEY` env var or settings.php |

No code changes required.
