# AGENTS.md — Component Ownership & Boundaries

> Defines which component owns which responsibility. Prevents duplication.
> Updated every sprint. Last updated: Sprint 5.

---

## Guiding Principle

Each concern has exactly one owner. If two components share a concern, one is
wrong. When adding code, find the right owner rather than duplicating.

---

## Component Map

### Ingestion Pipeline (`ingestion/`)

| Script | Owns |
|--------|------|
| `crawler.py` | HTTP fetch + crawl scope. Saves HTML/PDFs to `data/`. |
| `extractor.py` | HTML → clean text. No chunking logic. |
| `chunker.py` | Split text into retrieval-sized chunks with stable IDs. |
| `embedder.py` | Send chunk text to Azure OpenAI embeddings endpoint. |
| `store.py` | SQLite read/write for chunks, embeddings, pages. Corpus hash. |
| `corpus_guard.py` | Ingest-time injection scanner. Source of truth for injection patterns in the ingestion pipeline. |
| `retrieve.py` | Load index, cosine similarity, return top-K. Dev/smoke-test tool only. |
| `run_pipeline.py` | Orchestrator — calls the above. Manifest writing. --dry-run, --verify flags. |
| `config.py` | Load config from `.env` / environment. No defaults that contain secrets. |

**What ingestion pipeline owns:**
- All Python-side corpus writing and integrity checks
- Injection scanning at ingest time (via `corpus_guard.py`)
- SHA-256 chunk hashing (`store.py`)
- Index manifest (`data/index-manifest.json`)
- `--dry-run` and `--verify` workflows

**What ingestion pipeline does NOT own:**
- Drupal request handling
- PHP-side similarity search
- Admin UI display (reads manifest, does not write it)

---

### Drupal Module (`drupal/dcpas_chatbot/`)

| Service / Class | Owns |
|-----------------|------|
| `ChatController` | Request validation pipeline (content-type, JSON decode, auth, CSRF, flood, input normalisation, injection guard, retrieval, audit log). Orchestrates — no business logic inline. |
| `Retriever` | Loads VectorStore, computes cosine similarity, returns top-K. |
| `VectorStore` | MySQL/DB reads for chunks and embeddings. Memory-safe batch loading. Manifest reading. Schema awareness. |
| `PromptBuilder` | System prompt, user message assembly, citation extraction. |
| `AzureOpenAIClient` | HTTP call to Azure OpenAI chat completions. Timeout handling. |
| `SettingsForm` | Admin config UI. Reads manifest via VectorStore. No business logic. |
| `ChatbotBlock` | Block plugin. Template rendering + drupalSettings injection. |

**What Drupal module owns:**
- All PHP-side request handling and retrieval
- PHP-side injection filter (`PROMPT_INJECTION_PATTERNS` in `ChatController`)
- Memory-safe corpus loading (`VectorStore`)
- Admin UI manifest display (reads `index-manifest.json`, does not write it)

**What Drupal module does NOT own:**
- Writing chunk hashes or the manifest (ingestion pipeline owns this)
- Running the crawler or embedder
- Ingest-time injection scanning (corpus_guard.py owns this)

---

## Injection Pattern Sync

`ChatController::PROMPT_INJECTION_PATTERNS` and `corpus_guard.PATTERNS` must be
kept in sync. When you add a pattern to one, add it to the other. Each file has
a comment noting this obligation.

**Why two lists?** The ingestion pipeline is Python; the Drupal module is PHP.
Sharing a file is not practical. The obligation to sync is the documented contract.

---

## Corpus Integrity Ownership

```
Ingestion pipeline        Drupal module
─────────────────────    ─────────────────
corpus_guard.py           (mirrors patterns — PHP side)
  → scans at ingest        ChatController → scans at query
store.py                  VectorStore
  → writes text_hash        → validates NaN/INF, URL scheme
run_pipeline.py           SettingsForm
  → writes manifest         → reads manifest (display only)
```

The ingestion pipeline is the **trust root**. It decides what enters the corpus.
The Drupal module applies defence-in-depth at query time but cannot repair a
poisoned corpus. If `--verify` reports mismatches, rebuild the index.

---

## No-Duplication Rules

1. **Do not put cosine similarity logic in `run_pipeline.py`.** `retrieve.py` owns it.
2. **Do not put HTTP/API call logic in `ChatController`.** `AzureOpenAIClient` owns it.
3. **Do not put prompt text in `ChatController`.** `PromptBuilder` owns it.
4. **Do not put corpus scanning logic in `VectorStore.php`.** `corpus_guard.py` owns ingest scanning; `ChatController` owns query-time scanning.
5. **Do not write the manifest from PHP.** Only `run_pipeline.py` writes it.
