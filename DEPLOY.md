# DEPLOY.md — Deployment Guide

> Step-by-step guide for deploying the DCPAS RAG Chatbot on a Drupal 10 host.
> For demo deployments using standard OpenAI, steps are the same — substitute
> `OPENAI_API_BASE=https://api.openai.com/v1` where Azure settings are shown.

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Drupal 10.x | Drupal 11 compatibility not yet tested |
| PHP 8.1+ | Requires `intl` extension for homoglyph normalization |
| Composer | For module dependencies |
| Python 3.10+ | Ingestion pipeline (stdlib only — no pip packages required) |
| Drush 12+ | For healthcheck and module management |
| SQLite 3 | For ingestion pipeline index (`python3 -c "import sqlite3; print(sqlite3.version)"`) |

---

## Step 1 — Copy the module

```bash
cp -r drupal/dcpas_chatbot /path/to/drupal/web/modules/custom/dcpas_chatbot
```

Or symlink for development:
```bash
ln -s /path/to/drupal-rag-chatbot/drupal/dcpas_chatbot \
      /path/to/drupal/web/modules/custom/dcpas_chatbot
```

---

## Step 2 — Enable the module

```bash
cd /path/to/drupal
drush en dcpas_chatbot -y
drush cr
```

This creates three database tables:
- `dcpas_chatbot_chunks`
- `dcpas_chatbot_embeddings`
- `dcpas_chatbot_index_versions`

---

## Step 3 — Set the API key

**Recommended (production):** Set via environment variable so the key never
enters the Drupal database or config exports.

```bash
export DCPAS_OPENAI_API_KEY="your-openai-or-azure-key"
```

See `drupal/dcpas_chatbot/config/README.md` for Azure Key Vault and
`settings.php` injection patterns.

---

## Step 4 — Configure the module

Navigate to: **Admin → Config → DCPAS Chatbot Settings**
(`/admin/config/dcpas-chatbot/settings`)

Required fields:
- **Provider:** `Standard OpenAI` (demo) or `Azure OpenAI` (FedRAMP production)
- **API Base URL:**
  - Standard OpenAI: `https://api.openai.com/v1`
  - Azure: `https://{resource-name}.openai.azure.com/openai`
- **Azure API Version:** e.g. `2024-02-01` (Azure only; leave blank for standard OpenAI)
- **Embedding model:** `text-embedding-3-small` (standard) or Azure deployment name
- **Chat model:** `gpt-4o` (standard) or Azure deployment name
- **Enable chatbot:** Check to activate

Optional but recommended:
- **Max chunks:** `10000` for production (lower = faster, less memory)
- **Manifest path:** Absolute path to `data/index-manifest.json` (shows corpus status)

---

## Step 5 — Run the ingestion pipeline

On the host where the ingestion pipeline lives (may be same or different host):

```bash
cd /path/to/drupal-rag-chatbot

# Copy and configure environment
cp .env.example .env
# Edit .env — set OPENAI_API_KEY, OPENAI_API_BASE (Azure), model names

# Run full pipeline: crawl dcpas.osd.mil + embed all pages
make ingest

# Or step-by-step:
python3 ingestion/run_pipeline.py --crawl --embed

# Check results
python3 ingestion/run_pipeline.py --stats
```

Expected output:
```
Pages:    ~200–500
Chunks:   ~2000–8000
Embedded: same as chunks
```

---

## Step 6 — Export index to Drupal (if on separate host)

If the ingestion pipeline runs on a separate machine from Drupal:

```bash
# Export SQLite → MySQL-compatible SQL
python3 ingestion/export_mysql.py > data/dcpas_export.sql

# Import into Drupal's MySQL database
mysql -u drupal_user -p drupal_db < data/dcpas_export.sql
```

If co-located (SQLite on same host as Drupal), configure Drupal to read from
the SQLite file directly (update `VectorStore.php` connection, or use the
MySQL export path above).

---

## Step 7 — Verify index integrity

```bash
make verify
# or: python3 ingestion/run_pipeline.py --verify
```

Expected output:
```
=== Corpus Integrity Verification ===
  Total chunks:    3421
  Hash OK:         3421
  Hash mismatch:   0
  No hash stored:  0
All stored hashes verified OK.
```

---

## Step 8 — Run health check

```bash
make healthcheck
# or: drush dcpas:healthcheck
```

All checks should show `[✓]`. Address any `[✗]` items before going live.

---

## Step 9 — Place the chatbot block

1. Go to **Structure → Block layout** in the Drupal admin.
2. Find **DCPAS Chatbot** in the block list.
3. Place it in a region on the desired pages.
4. Save.

---

## Step 10 — Smoke test

Ask 5 known questions that should have answers in the corpus:

| Question | Expected source |
|----------|----------------|
| What is DCPAS? | dcpas.osd.mil (main page) |
| How do I apply for a federal job? | dcpas.osd.mil/hiring |
| What is the GS pay scale? | dcpas.osd.mil/pay |
| How does DCPAS support workforce development? | dcpas.osd.mil/workforce |
| What is MyBiz+? | dcpas.osd.mil/mybizplus |

Each answer should cite a `dcpas.osd.mil` source URL.

---

## Maintenance

### Re-indexing after site content changes
```bash
make ingest     # Full re-crawl and embed
make verify     # Confirm integrity
```

### Checking index health
```bash
make healthcheck
cat data/index-manifest.json
```

### Disabling the chatbot temporarily
Go to Admin → Config → DCPAS Chatbot Settings and uncheck **Enable chatbot**.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| "Chatbot is currently unavailable" | Not enabled or API key missing | Check admin settings; set `DCPAS_OPENAI_API_KEY` |
| Empty answers / no citations | Index not populated | Run `make ingest` |
| Slow responses (>5s) | Too many chunks loaded | Lower `max_chunks` in admin settings |
| 403 errors in logs | CSRF token expired | Normal after long idle; user should reload page |
| Hash mismatches in `--verify` | Possible corruption | Rebuild index: `make ingest` |
