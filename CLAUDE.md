# CLAUDE.md — DCPAS RAG Chatbot Architecture Reference

> This file documents architectural decisions, design rationale, and component
> boundaries for this project. Updated every sprint. Last updated: Sprint 8.

## Engineering North Star

| Principle | What it means here |
|-----------|-------------------|
| **Modularity** | Every PHP service, Python script, and JS component does one thing. |
| **No hacky solutions** | Security patches go to the root cause. No workarounds. |
| **Build for understandability** | Readable by a new dev on day one. Comments explain *why*. |
| **No god scripts** | `ChatController` orchestrates only. Services own their logic. |
| **Keep docs updated** | TOOLBOX.md, CLAUDE.md, and AGENTS.md ship with every sprint. |

---

## Ingestion Pipeline (Sprint 1)

### Architecture
Python stdlib-only pipeline in `ingestion/`. Five single-responsibility scripts:

| Script | Responsibility |
|--------|---------------|
| `crawl.py` | HTTP fetch + scope control for dcpas.osd.mil |
| `extract.py` | HTML → clean text (no third-party parser) |
| `chunk.py` | Split text into retrieval-sized chunks with stable IDs |
| `embed.py` | Send chunks to Azure OpenAI embeddings endpoint |
| `store.py` | Write chunks + vectors to SQLite |
| `retrieve.py` | Load index, compute cosine similarity, return top-K |
| `run_pipeline.py` | Orchestrator — calls the above in order |

### Vector Store
- SQLite database at `data/chatbot.db`
- Tables: `dcpas_chatbot_chunks`, `dcpas_chatbot_embeddings`, `dcpas_chatbot_index_versions`
- Cosine similarity computed in application code (no pgvector dependency for MVP)
- Hard cap: 50,000 rows loaded into PHP memory. See Sprint 5 for memory ceiling guard.

### Design Decision: stdlib only
Runtime Python tooling uses Python stdlib only — no third-party packages. Rationale: FedRAMP environments have strict package approval processes. A stdlib pipeline can be deployed without a package audit.

---

## Drupal Module (Sprint 2)

### Request Pipeline
```
POST /api/dcpas-chatbot/chat
  1. Content-Type check
  2. JSON decode
  3. Permission check       (403 + warning log)
  4. CSRF validation        (403 + warning log)
  5. Flood / rate limit     (429 + warning log)
  6. Input normalisation    (strip_tags → homoglyph normalize → length check)
  7. Prompt injection guard (blocklist patterns)
  8. Retrieve → build prompt → Azure call
  9. Audit log              (sha256(question), uid, IP, chunk count)
 10. Sanitised JSON response
```

### Service Boundaries
| Service | Owns |
|---------|------|
| `ChatController` | Request validation pipeline. Orchestrates services. No business logic. |
| `Retriever` | Loads VectorStore, computes cosine similarity, returns top-K chunks. |
| `VectorStore` | Database reads for chunks and embeddings. Schema awareness. |
| `PromptBuilder` | System prompt text, user message assembly, citation extraction. |
| `AzureOpenAIClient` | HTTP call to Azure OpenAI chat completions endpoint. |
| `SettingsForm` | Admin config UI — Azure credentials, rate limits, top-K, enable/disable. |
| `ChatbotBlock` | Block plugin. Renders widget template, injects drupalSettings. |

---

## Prompt Injection Design (Sprint 4)

### What we protect against
User input that corrupts the RAG prompt template structure (e.g. injecting
`[Source 1]` markers, `Question:` headers, or role-hijack phrases like
`System:`, `Disregard`, `Ignore all`).

### Controls (layered)
1. **Unicode homoglyph normalization** — `normalizer_normalize($input, FORM_KC)` before pattern matching, so lookalike characters (Cyrillic, Greek) don't bypass the blocklist.
2. **Blocklist (`PROMPT_INJECTION_PATTERNS`)** — strips structural markers and known injection phrases via regex.
3. **Length cap** — 500 characters max (post-strip-tags).
4. **strip_tags** — removes HTML before any other processing.
5. **Server-side system prompt** — the authoritative trust boundary. Even if injection bypasses all client-side and input filters, the system prompt instructs the model to answer only from retrieved context.

### Known limitation
This is best-effort defence-in-depth. A sufficiently novel injection phrase will not be on the blocklist. Document this in admin training. This control reduces the attack surface but does not eliminate the risk. See SECURITY.md.

---

## Audit Logging (Sprint 4)

Logging uses Drupal's standard `LoggerInterface` (PSR-3). Channel: `dcpas_chatbot`.

- Questions are **never** logged in plaintext — SHA-256 hash only.
- Warning logs on all 403, 429, and API error paths (uid + IP).
- Error log on API failure (exception message, internal only).

See SECURITY.md § Audit Log Schema for the full field list.

---

## Corpus Trust Model (Sprint 5)

The corpus goes through four validation layers, each owned by a different component:

| Layer | Owner | What it checks |
|-------|-------|---------------|
| Ingest scan | `corpus_guard.py` | Injection patterns in chunk text — same list as `ChatController`. Skip+log poisoned chunks. |
| Ingest hash | `store.py` | SHA-256 of chunk text stored in `chunks.text_hash` at write time. |
| Index manifest | `run_pipeline.py` | After each run: total chunks, skipped chunks, corpus fingerprint. Written to `data/index-manifest.json`. |
| Load validation | `VectorStore.php` | URL scheme check, NaN/INF vector check, finite numeric check on every loaded row. |

See AGENTS.md for ownership boundaries — corpus integrity is an ingestion concern, not a Drupal module concern.

### Corpus hash
`store.py::corpus_hash()` computes SHA-256 over all chunk_ids sorted lexicographically. Stable across re-runs if the chunk set is unchanged. Shown in the admin UI manifest section and written to the manifest JSON.

### Verify workflow
```bash
python3 ingestion/run_pipeline.py --verify
```
Recomputes SHA-256 for every chunk's text and compares to stored `text_hash`. Reports mismatches (possible tampering) and displays the manifest.

---

## Memory Safety (Sprint 5)

### Why batched loading?
`VectorStore::loadAllWithEmbeddings()` loads the full corpus into PHP memory for in-process cosine similarity. On large corpora this can exhaust PHP's memory_limit. The batch loader prevents runaway allocation.

### How it works
- Loads in batches of `LOAD_BATCH_SIZE` (1 000 rows).
- Before each batch, checks `memory_get_usage(TRUE)` against `MEMORY_CEILING_FRACTION` (80 %) of PHP's `memory_limit`.
- If the ceiling is approached, logs a `warning` to `dcpas_chatbot` channel and stops loading — returning a partial corpus with a logged warning. Retrieval continues on the loaded subset.
- The configurable `max_chunks` setting is the normal operational cap (default 10 000).
- `ABSOLUTE_ROW_CAP` (50 000) is a hard ceiling regardless of config.

### Threshold
`MEMORY_CEILING_FRACTION = 0.80` — stops at 80 % of `memory_limit`. This leaves headroom for the rest of the request cycle (similarity computation, prompt building, Azure call). Document this if raising the threshold.

### When to migrate
If `max_chunks = 10 000` is insufficient for retrieval quality at your corpus size, increase it up to 50 000 and monitor memory usage. If 50 000 chunks approach the memory ceiling, it is time to migrate to pgvector (Sprint 8) rather than raise PHP's memory_limit.

---

## Citation Trust Chain

1. **Ingest time (Python):** `store.py` validates source URLs before writing to SQLite.
2. **Ingest scan (Python):** `corpus_guard.py` rejects chunks containing injection patterns.
3. **Load time (PHP):** `VectorStore::loadAllWithEmbeddings()` validates URL scheme (`http`/`https`) before returning chunks. Rejects `javascript:`, `data:`, etc.
4. **Vector validation (PHP):** All vector elements checked for `is_float`/`is_int` AND `is_infinite`/`is_nan` to prevent cosine similarity arithmetic errors.
5. **Render time (JS):** `chatbot.js` checks `cite.url.startsWith('https://')` before setting `a.href`. Defence-in-depth against any URL that passed server-side checks.

---

## Configuration

All runtime config lives in Drupal config `dcpas_chatbot.settings`:

| Key | Default | Purpose |
|-----|---------|---------|
| `enabled` | `true` | Global chatbot on/off switch |
| `provider` | `openai` | API provider: `openai` or `azure` |
| `openai_api_key` | `''` | API key (prefer `DCPAS_OPENAI_API_KEY` env var in production) |
| `openai_api_base` | `https://api.openai.com/v1` | API base URL; set to Azure endpoint for FedRAMP |
| `openai_api_version` | `''` | Azure API version (e.g. `2024-02-01`); blank for standard OpenAI |
| `embedding_model` | `text-embedding-3-small` | Embedding model or Azure deployment name |
| `chat_model` | `gpt-4o` | Chat model or Azure deployment name |
| `top_k` | `5` | Chunks retrieved per query |
| `min_score` | `0.70` | Minimum cosine similarity threshold |
| `max_response_tokens` | `800` | Max tokens in LLM response |
| `api_timeout` | `15` | Seconds before API call times out |
| `system_prompt` | *(see install YML)* | Instructions prepended to every chat request |
| `rate_limit_window` | `60` | Flood window (seconds) |
| `rate_limit_max` | `10` | Max requests per window per IP |
| `chatbot_title` | `DCPAS Assistant` | Widget heading |
| `placeholder_text` | *(see install YML)* | Input field placeholder |
| `max_chunks` | `10000` | Max corpus chunks loaded into PHP memory |
| `manifest_path` | `''` | Filesystem path to `index-manifest.json` for admin display |

**Never commit real credentials.** See `drupal/dcpas_chatbot/config/README.md` for
the full secrets management guide (Azure Key Vault, settings.php injection, env var precedence).

---

## Production Secrets Model (Sprint 6)

### Precedence (highest to lowest)
1. `DCPAS_OPENAI_API_KEY` environment variable — never touches the database
2. `settings.php` `$config` override — in non-committed local settings file
3. Drupal config `openai_api_key` — for demo/dev only; blank in production

### FedRAMP path
1. API key stored in Azure Key Vault
2. App Service identity granted `Key Vault Secrets User` role
3. Key Vault reference mapped to `DCPAS_OPENAI_API_KEY` env var
4. Module picks it up via `getenv('DCPAS_OPENAI_API_KEY')`

Never chain the exception from the Guzzle HTTP client — it may contain Azure tenant
IDs or resource names. `AzureOpenAIClient::request()` wraps all exceptions before
re-throwing. This is intentional.

---

## WCAG 2.1 AA Compliance (Sprint 6)

### What is implemented
| WCAG criterion | Implementation |
|----------------|---------------|
| 1.3.1 Info and Relationships | Semantic HTML: `<form>`, `<label>`, `<button>`, heading hierarchy |
| 1.4.4 Resize Text | CSS uses relative units; no fixed pixel font sizes |
| 2.1.1 Keyboard | All controls keyboard-accessible; Enter to submit; Escape returns focus to input |
| 2.4.3 Focus Order | DOM order matches visual order; focus stays within widget |
| 3.1.1 Language of Page | `lang="en"` on widget container |
| 3.1.2 Language of Parts | `lang="en"` on assistant response `<p>` elements |
| 4.1.2 Name, Role, Value | ARIA: `role="log"`, `aria-live="polite"`, `aria-label`, `aria-required`, `aria-busy` |
| 4.1.3 Status Messages | `aria-busy="true"` on form while awaiting response; messages region uses `role="log"` |

### What is NOT formally tested
- Color contrast ratios (`chatbot.css`) — admin should run through a contrast checker
- Screen reader testing with NVDA/JAWS — recommended before production launch
- Mobile/touch interaction — not formally audited

---

## Vector Store Backends (Sprint 8)

### Architecture
All vector store access goes through `VectorStoreInterface`. The active service (`dcpas_chatbot.vector_store`) is `VectorStoreLocator`, which reads `vector_store_backend` config and delegates to either `SqliteVectorStore` or `PgVectorStore` on every call.

| Backend | Class | How similarity works | When to use |
|---------|-------|---------------------|-------------|
| `sqlite` (default) | `SqliteVectorStore` | Load corpus into PHP memory, compute cosine similarity in-process | Up to ~50K chunks; default for all deployments |
| `pgvector` | `PgVectorStore` | Single `<=>` ANN query in PostgreSQL | 50K+ chunks; or when in-process memory is constrained |

### Switching backends
Change `vector_store_backend` in admin settings (or via config). The switch takes effect immediately — no cache flush or service rebuild required. `VectorStoreLocator` reads config on every call.

### Cosine similarity: where it lives
- **SQLite path:** `SqliteVectorStore::cosineSimilarity()` — pure PHP, same algorithm as before Sprint 8.
- **pgvector path:** `e.embedding <=> vec::vector` — the `<=>` operator computes cosine distance in PostgreSQL. Score = `1 - distance`.
- `Retriever.php` no longer owns similarity computation — it just calls `findSimilar()`.

### pgvector table
`dcpas_chatbot_pg_embeddings` — created by `hook_update_9801()` on PostgreSQL installs. Not in `hook_schema()` because Drupal's schema API does not support `vector(N)` column types. The IVFFlat index uses `lists = sqrt(corpus_size)` (min 10, max 1000).

### Migration
`ingestion/migrate_to_pgvector.py` reads `data/index.sqlite` and upserts into PostgreSQL. Idempotent — safe to re-run after adding new chunks. Requires `psycopg2-binary` and `pgvector` Python packages (not stdlib). See `DEPLOY.md § pgvector Setup`.

---

## Confidence Scoring & Evaluation (Sprint 7)

### Low-confidence fallback
When `Retriever::retrieve()` returns an empty array (no chunks met `min_score` threshold), `ChatController` triggers the fallback path:
1. Returns the "couldn't find relevant information" message to the user.
2. Logs a `warning` to `dcpas_chatbot` channel with `uid`, `ip`, and `q_hash` (SHA-256 hash of the question, no plaintext).

**Why log low-confidence queries?** They reveal gaps in corpus coverage or questions that need different phrasing. Reviewing the hash list tells admins which query shapes fail without logging PII.

**The min_score threshold** (default: 0.70) is configurable via the admin UI. Raising it reduces false-positive retrievals but increases low-confidence fallbacks. 0.70 was chosen empirically as a reasonable default for this domain.

### Retrieval evaluation
`ingestion/evaluate.py` measures retrieval accuracy against a fixture set:
- Fixtures: `tests/eval/fixtures.json` — 22 Q&A pairs, each with a question and expected source URL prefixes.
- A "hit" is when any retrieved chunk's `source_url` starts with any expected URL.
- Reports: top-1 hit rate, top-3 hit rate, mean top score.
- Thresholds: top-1 ≥ 70% = good; 50–70% = acceptable; < 50% = poor (review corpus coverage).
- CI job `retrieval-eval` runs `--strict` mode when `CI_EVAL_ENABLED=true` and an index artifact is present.

**Fixture design rationale:** Expected URLs are prefix-matched because a single page produces many chunks with different chunk_ids. Exact URL matching would be too fragile. The fixture set should grow as new pages are added to the corpus.

---

## Performance Logging (Sprint 6)

`ChatController::chat()` records three timings per successful request:
- `retrieve_ms` — embedding + cosine similarity scan
- `azure_ms` — Azure/OpenAI HTTP roundtrip
- `total_ms` — wall clock from request entry to response

Logged at `info` level to `dcpas_chatbot` channel. Never includes question text.
See `PERFORMANCE.md` for thresholds and migration triggers.
