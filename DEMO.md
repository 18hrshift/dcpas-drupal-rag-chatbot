# DEMO.md — dvapp21 / dcpas-dev Deployment Guide

> Exact commands for deploying the chatbot to the dcpas-dev environment.
> Ingestion runs on the **OpenClaw VM**. The Drupal module runs on **dvapp21**.

---

## Environment Summary

| Item | Value |
|------|-------|
| Server | dvapp21 |
| Drupal root | `/var/www/html/dcpas-dev/web` |
| Drush | `/var/www/html/dcpas-dev/vendor/bin/drush --root=/var/www/html/dcpas-dev/web` |
| PHP | 8.1.34 |
| PHP intl | NOT installed (normalization skipped — see note below) |
| DB | MySQL — `44063_DCPAS-DEV2` |
| Private files | `/var/www/html/shared/dcpas-dev-private` |
| Modules path | `web/modules/` (no `custom/` subdirectory) |
| Provider for demo | Standard OpenAI |

---

## Known Limitation: intl Extension Missing

The PHP `intl` extension is not installed on dvapp21. This means:

- **Unicode homoglyph normalization is skipped** — Cyrillic/Greek lookalike
  characters in user input will not be caught by the injection filter.
- Everything else works normally.
- For production (FedRAMP), install `php-intl` before go-live.

---

## Step 1 — Run the Ingestion Pipeline (on the OpenClaw VM)

```bash
cd /home/openclawjb/projects/drupal-rag-chatbot

# Configure API key
cp .env.example .env
# Edit .env — set OPENAI_API_KEY to your standard OpenAI key
#   OPENAI_API_KEY=sk-...
#   EMBEDDING_MODEL=text-embedding-3-small
#   CHAT_MODEL=gpt-4o
#   TARGET_URL=https://dcpas.osd.mil
#   MAX_PAGES=500

# Run the full pipeline
cd ingestion/
python3 run_pipeline.py

# Verify the index
python3 run_pipeline.py --verify
```

---

## Step 2 — Export SQLite Index to MySQL SQL Dump (on the OpenClaw VM)

```bash
cd /home/openclawjb/projects/drupal-rag-chatbot

# Check if Drupal uses a table prefix — run on dvapp21:
#   grep 'prefix' /var/www/html/dcpas-dev/web/sites/default/settings.php
# If 'prefix' => '' or prefix is empty, use no --table-prefix argument.
# If 'prefix' => 'drupal_', use: --table-prefix drupal_

python3 ingestion/export_mysql.py \
  --out data/export.sql
  # --table-prefix drupal_    ← add if needed
```

---

## Step 3 — Copy Module and SQL Dump to dvapp21

```bash
# Copy the Drupal module
scp -r drupal/dcpas_chatbot/ dvapp21:/var/www/html/dcpas-dev/web/modules/

# Copy the SQL dump
scp data/export.sql dvapp21:/tmp/dcpas_export.sql

# Copy the index manifest (for admin UI display)
scp data/index-manifest.json dvapp21:/var/www/html/shared/dcpas-dev-private/dcpas-index-manifest.json
```

---

## Step 4 — Enable the Module on dvapp21

```bash
/var/www/html/dcpas-dev/vendor/bin/drush \
  --root=/var/www/html/dcpas-dev/web \
  en dcpas_chatbot -y
```

---

## Step 5 — Import the Corpus into MySQL on dvapp21

```bash
# Get MySQL credentials from settings.php
grep -A5 "'default'" /var/www/html/dcpas-dev/web/sites/default/settings.php | grep -E "host|user|pass|dbname"

# Import
mysql -h HOST -u USER -p 44063_DCPAS-DEV2 < /tmp/dcpas_export.sql
```

---

## Step 6 — Configure the Module

Go to: `/admin/config/dcpas-chatbot/settings`

| Field | Value for demo |
|-------|---------------|
| Enable chatbot | ✓ checked |
| Provider | Standard OpenAI |
| API Key | Your `sk-...` key (or set `DCPAS_OPENAI_API_KEY` env var on dvapp21) |
| API Base URL | `https://api.openai.com/v1` |
| Azure API Version | *(leave blank)* |
| Embedding model | `text-embedding-3-small` |
| Chat model | `gpt-4o` |
| Vector store backend | `sqlite` (default — uses MySQL, not literal SQLite) |
| Index manifest path | `/var/www/html/shared/dcpas-dev-private/dcpas-index-manifest.json` |

> **Setting the API key via environment variable (recommended):**
> Add to `/etc/environment` or the php-fpm service file on dvapp21:
> ```
> DCPAS_OPENAI_API_KEY=sk-...
> ```
> Then restart php-fpm. The env var takes precedence over the Drupal config field.

---

## Step 7 — Run Health Check

```bash
/var/www/html/dcpas-dev/vendor/bin/drush \
  --root=/var/www/html/dcpas-dev/web \
  dcpas:healthcheck
```

Expected output: all checks passed, index populated, API connectivity OK.

---

## Step 8 — Place the Block

1. Go to `/admin/structure/block`
2. Click **Place block** in the region where the chatbot should appear
3. Search for **DCPAS Chatbot**
4. Save

---

## Step 9 — Smoke Test

Visit a page where the block is placed. Ask: *"What is DCPAS?"*

Expect: a response with a citation link to `dcpas.osd.mil`.

---

## Drupal Table Prefix Check

If the import fails with "table not found" errors, check the Drupal prefix:

```bash
grep -A 20 "databases\['default'\]" \
  /var/www/html/dcpas-dev/web/sites/default/settings.php | grep prefix
```

Re-run the export with the correct `--table-prefix` if needed.

---

## Re-ingesting (after crawl updates)

```bash
# On the OpenClaw VM:
python3 ingestion/run_pipeline.py    # re-crawl and re-embed
python3 ingestion/export_mysql.py --out data/export.sql

# On dvapp21:
mysql -h HOST -u USER -p 44063_DCPAS-DEV2 < /tmp/dcpas_export.sql

# Clear Drupal cache (clears the vector store's query cache if any):
/var/www/html/dcpas-dev/vendor/bin/drush --root=/var/www/html/dcpas-dev/web cr
```
