# DCPAS RAG Chatbot — Production Roadmap

**Date:** 2026-03-21
**Status:** Active
**Goal:** Production-ready Drupal 10 RAG chatbot for non-classified U.S. government environments.
**Target:** Any unclassified Drupal 10 government site (dcpas.osd.mil or similar). FedRAMP-aligned. Accessible to real users.

---

## Engineering North Star

| Principle | What it means here |
|-----------|-------------------|
| **Modularity** | Every PHP service, Python script, and JS component does one thing. No cross-cutting concerns in one file. |
| **No hacky solutions** | Security patches go to the root cause. No regex-over-regex workarounds. No "temporary" config hacks. |
| **Build for understandability** | Every class and script is readable by a new Drupal/Python dev on day one. Comments explain *why*, not *what*. |
| **No god scripts** | `ChatController` orchestrates only. Services own their logic. Python pipeline scripts are single-responsibility. |
| **Keep docs updated** | `TOOLBOX.md`, `CLAUDE.md`, and `AGENTS.md` ship with every sprint. No sprint closes with stale docs. |

---

## Git Workflow

### Branch Model
```
main          ← production-ready, tagged releases only
develop       ← integration branch, all PRs merge here first
feature/*     ← new capabilities (e.g., feature/pgvector-migration)
fix/*         ← bug fixes and security patches (e.g., fix/prompt-injection-hardening)
docs/*        ← documentation-only changes (e.g., docs/security-md)
chore/*       ← tooling, deps, config (e.g., chore/gitignore-update)
```

### Commit Standard
```
<type>(<scope>): <short summary>

Types: feat | fix | docs | test | chore | refactor | security
Scope: drupal | ingestion | pipeline | config | tests | ci

Examples:
  security(drupal): harden prompt injection filter — expand blocklist and add INF/NaN guard
  feat(ingestion): add corpus integrity hash check on index write
  docs(all): update TOOLBOX, CLAUDE, AGENTS for Sprint 4
  fix(drupal): replace innerHTML spinner with programmatic DOM build
```

### PR Rules
- Every PR targets `develop`, not `main`
- PR description must include: **What**, **Why**, **Security impact** (none/mitigated/new)
- `main` merges are tagged (`v0.x.0`) with a release note
- No force-pushes to `main` or `develop`
- Squash-merge from `feature/*` and `fix/*` to keep history readable

---

## Current State (Post Sprint 3)

| Area | Status |
|------|--------|
| Ingestion pipeline | Complete — crawl, extract, chunk, embed, SQLite store |
| Drupal module | Complete — ChatController, block, settings, services |
| MVP polish | Complete — citations, rate limiting, audit logging |
| Security hardening | Complete — CSRF, permissions, XSS, SQL injection all addressed |
| Security review findings | **Closed** — all 5 Sprint 4 fixes shipped |
| Git workflow / CI | Complete — develop branch, CI workflow, PR template, CONTRIBUTING |
| Docs baseline | Complete — SECURITY.md, CLAUDE.md, TOOLBOX.md created Sprint 4 |
| Production deployment path | **Not started** — Sprint 6 |
| CI / automated tests | 47 tests in `tests/`, CI pipeline in `.github/workflows/ci.yml` |

---

## Sprint 4 — Security Remediation & Git Foundation

**Branch:** `fix/sprint-4-security-remediation`
**Goal:** Close all open security findings from the Rex review. Establish the git workflow and CI baseline.

### Security Fixes (from review)

- [x] **[fix/prompt-injection-hardening]** Expand prompt injection blocklist in `ChatController.php`:
  - Add: `System:`, `Assistant:`, `Override:`, `Final answer:`, `<EndOfContext>`, `Disregard`, `Ignore all`
  - Add Unicode homoglyph normalization before pattern matching
  - Document in `CLAUDE.md` that this is a best-effort control, not a guarantee
- [x] **[fix/nan-inf-vector-validation]** Add `is_infinite()` / `is_nan()` check in `VectorStore.php` vector loading
- [x] **[fix/innerHTML-spinner]** Replace `innerHTML` spinner with `document.createElement` loop in `chatbot.js`
- [x] **[fix/citation-href-validation]** Add client-side `startsWith('https://')` guard on citation URLs in `chatbot.js`
- [x] **[fix/audit-logging]** Add `$this->logger->warning()` calls on 403, 429, and API error paths in `ChatController.php`

### Git & CI Foundation
- [x] Initialize `develop` branch from current `main`
- [x] Add `CONTRIBUTING.md` — branch model, commit format, PR checklist
- [x] Add GitHub Actions (or Gitea/local CI) workflow:
  - PHP: `phpcs` with Drupal coding standards
  - Python: `python3 -m pytest tests/`
  - Lint: `eslint js/chatbot.js`
- [x] Add `.github/PULL_REQUEST_TEMPLATE.md` — What / Why / Security impact fields
- [x] Tag current `main` as `v0.3.0` (post-Sprint 3 baseline)

### Docs
- [x] Create `SECURITY.md` — threat model, known limitations, responsible disclosure note
- [x] Update `CLAUDE.md` — prompt injection design assumptions, audit log schema
- [x] Update `TOOLBOX.md` — git workflow section, CI commands

**North Star checks:**
- Modularity? Each fix is a single-responsibility diff. No coupling changes.
- No hacks? All fixes go to the root cause. No `// TODO: fix later`.
- Docs shipped? SECURITY.md created, CLAUDE.md and TOOLBOX.md updated.

---

## Sprint 5 — Corpus Integrity & Memory Stability

**Branch:** `feature/sprint-5-corpus-integrity`
**Goal:** Make the retrieval pipeline trustworthy — poison-resistant ingestion, stable chunking, and memory-safe query path.

### Corpus Integrity
- [x] **Corpus hash check:** SHA-256 of chunk text stored in `chunks.text_hash` at write time (`store.py`)
- [x] **Ingest-time keyword scan:** `corpus_guard.py` — same patterns as `ChatController`. Skip+log poisoned chunks before writing.
- [x] **Index manifest:** `data/index-manifest.json` written after each ingest: run_at, total_chunks, embedded_chunks, skipped_poisoned, corpus_hash
- [x] **Admin UI manifest display:** `SettingsForm.php` reads manifest via `VectorStore::getManifest()`, shows run_at, totals, corpus hash, poisoned count

### Memory Safety
- [x] PHP memory ceiling guard in `VectorStore::loadAllWithEmbeddings()` — batch loading (1 000 rows/batch), `memory_get_usage()` check before each batch, warning log if ceiling approached, partial return
- [x] Configurable `max_chunks` admin setting (default 10 000, hard cap 50 000). `manifest_path` config added for admin UI.

### Ingestion Pipeline
- [x] `--dry-run` flag: runs extract/chunk/scan steps, skips all writes, reports what would be indexed
- [x] `--verify` flag: loads index, re-derives hashes, reports mismatches and displays manifest

### Docs
- [x] Update `TOOLBOX.md` — manifest check, dry-run, verify commands
- [x] Create `AGENTS.md` — component ownership, corpus integrity boundary
- [x] Update `CLAUDE.md` — corpus trust model, memory ceiling rationale

**North Star checks:**
- Modularity? Corpus hash logic lives in ingestion pipeline, not Drupal. Admin display reads manifest only.
- No hacks? Memory ceiling is a configurable guard, not a silent truncation.
- Single responsibility? `store.py` writes, manifest is a separate post-write step.

---

## Sprint 6 — Production Deployment Path

**Branch:** `feature/sprint-6-production-deploy`
**Goal:** Make this deployable on a real government Drupal host. Secrets management, environment parity, deployment runbook.

### Secrets & Environment
- [x] Document Azure Key Vault integration path (`config/README.md`)
- [x] Add `settings.php` snippet for production secret injection (`config/README.md`)
- [x] Add `config/README.md` — secrets guidance, env var precedence, Key Vault path
- [x] Add secrets-leak pre-commit hook (`hooks/pre-commit`; install via `make install-hooks`)

### Deployment
- [x] `DEPLOY.md` — 10-step deployment guide (module install, ingest, verify, configure, smoke test)
- [x] `drush dcpas:healthcheck` — checks enabled, API key, URL, index, manifest, live API ping
- [x] `Makefile` — targets: ingest, embed, dry-run, verify, stats, healthcheck, test, lint, install-hooks
- [x] `.env.example` — already complete (updated in docs audit)

### Accessibility & UX (WCAG 2.1 AA)
- [x] Keyboard navigation: Enter to submit (existed), Escape to return focus to input (added)
- [x] `aria-busy="true"` on form during API request (screen reader signals loading state)
- [x] `lang="en"` on widget container (template) and on assistant response paragraphs (JS)
- [x] `role="log"` + `aria-live="polite"` on messages region (existed — announces new content)
- [x] Loading element has `aria-label="Thinking…"` inside the live region

### Performance Baseline
- [x] Response time logging in `ChatController`: `total_ms`, `retrieve_ms`, `azure_ms` per request
- [x] `PERFORMANCE.md` — thresholds, O(n×d) retrieval analysis, pgvector migration triggers, log queries

### Docs
- [x] `DEPLOY.md` created
- [x] `TOOLBOX.md` — Makefile targets, healthcheck, pre-commit hook (updated below)
- [x] `CLAUDE.md` — production secrets model, WCAG approach (updated below)

**North Star checks:**
- No hacks? `drush healthcheck` tests real config, not mock state.
- Understandability? `DEPLOY.md` usable by a government Drupal admin with no Python background.
- Modularity? `healthcheck` is a separate Drush plugin, not folded into `ChatController`.

---

## Sprint 7 — Evaluation & Confidence Scoring

**Branch:** `feature/sprint-7-evaluation`
**Goal:** Give admins and developers tools to measure and improve retrieval quality over time.

### Evaluation Framework
- [x] Build `tests/eval/` — 22 Q&A fixture pairs mapped to expected source URL prefixes
- [x] Add `ingestion/evaluate.py` — runs eval fixtures against live index, reports:
  - Top-1 hit rate (was the right source in the top chunk?)
  - Top-3 hit rate
  - Mean top cosine similarity score
- [x] Add optional eval step to CI (`retrieval-eval` job, runs when `CI_EVAL_ENABLED=true`)
- [x] Document eval methodology in `AGENTS.md`

### Confidence Scoring
- [x] Minimum similarity threshold (0.70) already implemented in Retriever.php
- [x] Fallback message already implemented in ChatController
- [x] Log low-confidence queries (hash only, no question text) — added warning log in ChatController when empty($chunks)

### Docs
- [x] Update `TOOLBOX.md` — eval commands, interpreting results, `make eval`
- [x] Update `AGENTS.md` — eval ownership, how to extend fixture set
- [x] Update `CLAUDE.md` — confidence scoring design, fallback behavior rationale

---

## Sprint 8 — Vector Store Migration Path (pgvector)

**Branch:** `feature/sprint-8-pgvector`
**Goal:** Provide a first-class migration path off SQLite in-process cosine search to pgvector for production-scale deployments.

> This sprint is explicitly scope-gated: only implement if deployment target has PostgreSQL available.
> SQLite path remains supported and tested.

- [ ] Add `VectorStoreInterface` — both `SqliteVectorStore` and `PgVectorStore` implement it
- [ ] Implement `PgVectorStore` using Drupal's Database API + pgvector extension
- [ ] Add migration script `ingestion/migrate_to_pgvector.py`
- [ ] Update admin settings: vector store backend selector (sqlite / pgvector)
- [ ] Update `DEPLOY.md` with pgvector setup section
- [ ] Benchmarks: compare query latency at 10K, 50K, 100K chunks

---

## Release Plan

| Tag | Sprint | What ships |
|-----|--------|-----------|
| `v0.3.0` | Sprint 3 (done) | MVP + security hardening baseline |
| `v0.4.0` | Sprint 4 | Security fixes + git workflow + CI |
| `v0.5.0` | Sprint 5 | Corpus integrity + memory safety |
| `v0.6.0` | Sprint 6 | Production deployment path + WCAG |
| `v0.7.0` | Sprint 7 | Evaluation + confidence scoring |
| `v1.0.0` | Sprint 8 | pgvector + production-validated release |

---

## Open Questions

1. **Hosting model** — Is Drupal on the same host as the ingestion pipeline, or is the SQLite index built separately and rsync'd over?
2. **Crawl authorization** — Is there a robots.txt or crawl agreement needed for dcpas.osd.mil?
3. **PDF handling** — `pdf_extractor.py` exists but is it being used in production runs?
4. **Azure deployment names** — Embedding and GPT-4 deployment names for the target Azure tenant need confirming before Sprint 6.
5. **pgvector availability** — Does the target PostgreSQL host have the pgvector extension? Gates Sprint 8.
6. **Drupal version target** — Drupal 10 only, or also 11 compatibility needed?

---

## Files to Keep Current

| File | Updated by | When |
|------|-----------|------|
| `ROADMAP.md` | Yorgos | Each sprint planning session |
| `TOOLBOX.md` | Every sprint | Operational commands and runbooks |
| `CLAUDE.md` | Every sprint | Architecture decisions, boundaries, design rationale |
| `AGENTS.md` | Every sprint | Component ownership and no-duplication rules |
| `SECURITY.md` | Sprint 4+ | Threat model, known limitations |
| `DEPLOY.md` | Sprint 6+ | Deployment runbook |
| `CHANGELOG.md` | Each release tag | What changed, what fixed, what known |
