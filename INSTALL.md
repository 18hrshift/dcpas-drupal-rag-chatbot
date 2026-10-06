# DCPAS RAG Chatbot — Installation Guide

A Drupal 10 module that adds an AI chatbot to your site. The chatbot answers questions using documents you provide — no live web crawling required for demo/dev use.

---

## What You Need Before Starting

| Requirement | Notes |
|-------------|-------|
| Drupal 10.x site | With admin access |
| Drush 12+ | For enabling the module |
| PHP 8.1+ | Already required by Drupal 10 |
| Python 3.10+ | For the ingestion pipeline (runs on your machine, not the server) |
| OpenAI API key | Standard OpenAI account at platform.openai.com |

---

## Part 1 — Install the Drupal Module

### Step 1 — Copy the module to your Drupal site

From this repository, copy the module folder into your Drupal custom modules directory:

```bash
cp -r drupal/dcpas_chatbot /path/to/your/drupal/web/modules/custom/dcpas_chatbot
```

Replace `/path/to/your/drupal` with the actual path to your Drupal installation.

### Step 2 — Enable the module

```bash
cd /path/to/your/drupal
drush en dcpas_chatbot -y
drush cr
```

This creates three new database tables for the chatbot index. It does not modify any existing Drupal tables or content.

### Step 3 — Configure the module

1. Go to **Admin → Configuration → DCPAS Chatbot Settings**
   (URL: `/admin/config/dcpas-chatbot/settings`)
2. Fill in the required fields:
   - **Provider:** Standard OpenAI
   - **API Base URL:** `https://api.openai.com/v1`
   - **Embedding model:** `text-embedding-3-small`
   - **Chat model:** `gpt-4o`
   - **API Key:** your OpenAI key
3. Check **Enable chatbot**
4. Click **Save**

> **Azure OpenAI (FedRAMP production):** Use `https://{resource}.openai.azure.com/openai` as the base URL and set your Azure deployment names instead of model IDs. See `DEPLOY.md` for details.

### Step 4 — Place the chatbot block

1. Go to **Structure → Block layout**
2. Find **DCPAS Chatbot** in the block list
3. Place it in your desired region
4. Save

The chatbot will appear on your site but show "unavailable" until the document index is loaded (Part 2).

---

## Part 2 — Load Documents into the Chatbot

This runs the ingestion pipeline on your local machine (or any server with Python). It reads your documents, breaks them into chunks, generates embeddings via the OpenAI API, and loads them into the database.

### Step 1 — Set up your API key

In the repository root, copy the example environment file and add your key:

```bash
cp .env.example .env
```

Open `.env` and fill in:
```
OPENAI_API_KEY=sk-your-key-here
```

Leave everything else at the defaults for standard OpenAI.

### Step 2 — Prepare your documents

Create a folder and put your source documents in it. Supported formats:

- `.txt` — plain text
- `.md` — markdown
- `.pdf` — PDF documents

```bash
mkdir demo-docs
# Copy your files into demo-docs/
```

### Step 3 — Dry run (optional but recommended)

Preview what the pipeline will ingest without writing anything:

```bash
python3 ingestion/run_pipeline.py --from-files ./demo-docs --dry-run
```

You'll see each file listed with its chunk count. No API calls are made, nothing is written.

### Step 4 — Run the ingestion

```bash
python3 ingestion/run_pipeline.py --from-files ./demo-docs
```

This will:
1. Read each document
2. Split it into overlapping chunks (~400 words each)
3. Send chunks to OpenAI for embedding (this costs a small amount of API credits)
4. Save everything to `data/index.sqlite`

### Step 5 — Load the index into Drupal's database

Export the index and import it into your Drupal database:

```bash
python3 ingestion/export_mysql.py > data/dcpas_export.sql
mysql -u YOUR_DB_USER -p YOUR_DB_NAME < data/dcpas_export.sql
```

Replace `YOUR_DB_USER` and `YOUR_DB_NAME` with your Drupal database credentials (found in your Drupal `settings.php`).

### Step 6 — Verify it works

Test retrieval from the command line:

```bash
python3 ingestion/run_pipeline.py --query "your test question here"
```

You should see matching chunks from your documents with relevance scores. Then try the chatbot on your Drupal site — it should now answer questions based on your documents.

---

## Switching to Live Crawl (Later)

When you're ready to index the actual site instead of demo documents, replace the `--from-files` command with:

```bash
python3 ingestion/run_pipeline.py --crawl --embed
```

Then re-run the export/import step (Step 5). Everything else stays the same.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "Chatbot is currently unavailable" | Check that **Enable chatbot** is checked in admin settings and that the API key is set |
| Chatbot gives empty answers | The index is empty — complete Part 2 |
| `Error: OPENAI_API_KEY not set` | Check your `.env` file has the key and no extra spaces |
| `drush: command not found` | Run `vendor/bin/drush` instead |
| MySQL import fails | Confirm your DB credentials and that the three `dcpas_chatbot_*` tables exist |

---

## What Does Not Get Committed to Git

The following are excluded from the repository and must be set up locally:

- `.env` — your API keys
- `data/` — the document index and crawled pages
- `sites/default/settings.local.php` — Drupal local config

Never commit API keys. If you accidentally do, rotate the key immediately.
