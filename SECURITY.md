# Security Policy — DCPAS RAG Chatbot

## Threat Model

### Assets
- Azure OpenAI API key (stored in Drupal config / environment variables)
- Site content corpus (SQLite/MySQL index — not classified, but must not be tampered with)
- User query data (PII concern — never logged in plaintext)

### Trust Boundaries
| Boundary | Control |
|----------|---------|
| User → Drupal | Drupal session auth + `access dcpas chatbot` permission |
| User → Chat endpoint | CSRF token validation (session-scoped) |
| Endpoint → Azure | API key in config, not in code |
| Corpus → Prompt | Server-side prompt template; user question injected as sanitized string |

### Known Attack Surfaces

#### Prompt Injection
- **Risk:** User crafts input that hijacks the RAG prompt template or changes model behavior.
- **Controls:** Input blocklist (structural markers + known role-hijack phrases), homoglyph normalization, 500-character length cap, `strip_tags()`.
- **Limitation:** This is a best-effort defence-in-depth layer. No blocklist is exhaustive. The server-side system prompt is the authoritative trust boundary; the filter is supplementary.

#### Corpus Poisoning
- **Risk:** Attacker poisons the crawled site content to inject malicious instructions into retrieved chunks.
- **Controls:** Source URL scheme validation (only `http`/`https`), citation URL guard (client-side `startsWith('https://')` check). Sprint 5 adds chunk-level injection scanning at ingest time.

#### XSS via Response
- **Risk:** Azure LLM returns content containing HTML/JS that is rendered unsafely.
- **Controls:** Server-side `strip_tags()` on LLM answer. Client renders answer via `textContent` (never `innerHTML`). Citation links built with `createElement` — no `innerHTML`.

#### Rate Abuse / DoS
- **Risk:** Attacker floods the chat endpoint to exhaust Azure token budget.
- **Controls:** Drupal Flood API rate limiting (per-IP, configurable window and max). Admin can disable the chatbot entirely.

#### Credential Exposure
- **Risk:** Azure API key committed to version control or logged.
- **Controls:** Key stored in Drupal config (not in code). Never logged. Sprint 6 adds a pre-commit hook to scan for API key patterns.

### Out of Scope (MVP)
- Classified or CUI data — this module is for unclassified public site content only.
- Full NIST 800-53 control coverage — Sprint 6 production hardening sprint addresses this.
- pgvector — SQLite in-process cosine search is the MVP vector store.

## Responsible Disclosure

This module is a demo/MVP targeting government Drupal deployments. If you find a
security issue:

1. Do **not** open a public GitHub issue.
2. Contact the project maintainer directly with a description of the finding,
   reproduction steps, and impact assessment.
3. Allow reasonable time for a fix before any public disclosure.

## Audit Log Schema

The `dcpas_chatbot` Drupal logger channel records:

| Level | Trigger | Fields logged |
|-------|---------|---------------|
| `info` | Successful request | uid, IP, SHA-256(question), chunk count |
| `warning` | 403 (permission) | uid, IP |
| `warning` | 403 (CSRF) | uid, IP |
| `warning` | 429 (rate limit) | uid, IP |
| `warning` | 500 (API failure) | uid, IP |
| `error` | 500 (API failure) | exception message |

Question text is **never** logged in plaintext — only its SHA-256 hash, for
correlation without PII exposure.
