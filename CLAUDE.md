# CLAUDE.md — DCPAS RAG Chatbot Architecture Reference

> This file documents architectural decisions, design rationale, and component
> boundaries for this project. Updated every sprint. Last updated: Sprint 4.

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

## Citation Trust Chain

1. **Ingest time (Python):** `store.py` validates source URLs before writing to SQLite.
2. **Load time (PHP):** `VectorStore::loadAllWithEmbeddings()` validates URL scheme (`http`/`https`) before returning chunks. Rejects `javascript:`, `data:`, etc.
3. **Vector validation (PHP):** All vector elements checked for `is_float`/`is_int` AND `is_infinite`/`is_nan` to prevent cosine similarity arithmetic errors.
4. **Render time (JS):** `chatbot.js` checks `cite.url.startsWith('https://')` before setting `a.href`. Defence-in-depth against any URL that passed server-side checks.

---

## Configuration

All runtime config lives in Drupal config `dcpas_chatbot.settings`:

| Key | Default | Purpose |
|-----|---------|---------|
| `enabled` | false | Global chatbot on/off switch |
| `openai_api_key` | — | Azure OpenAI API key |
| `openai_endpoint` | — | Azure OpenAI endpoint URL |
| `openai_deployment` | — | GPT-4 deployment name |
| `openai_embedding_deployment` | — | Embedding model deployment name |
| `openai_api_version` | — | Azure API version string |
| `top_k` | 5 | Chunks retrieved per query |
| `rate_limit_window` | 60 | Flood window (seconds) |
| `rate_limit_max` | 10 | Max requests per window |

**Never commit real credentials.** Use environment variables or Drupal's
`settings.php` secret injection. See Sprint 6 for full secrets management plan.
