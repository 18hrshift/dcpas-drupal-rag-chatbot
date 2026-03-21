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
- [ ] **Corpus hash check:** At index write time, compute SHA-256 of each chunk's text and store in `dcpas_chatbot_chunks`
- [ ] **Ingest-time keyword scan:** Before storing a chunk, scan for prompt-injection patterns (same list as `ChatController`). Log and skip poisoned chunks rather than silently indexing.
- [ ] **Index manifest:** At the end of each ingest run, write a manifest file (`data/index-manifest.json`) with: run timestamp, total chunks, skipped chunks, hash of full chunk list
- [ ] **Admin UI manifest display:** Show active index version + timestamp in the Drupal admin settings form

### Memory Safety
- [ ] Add PHP memory ceiling guard in `VectorStore::loadAllWithEmbeddings()`:
  - Check `memory_get_usage()` before loading next batch
  - Return partial result with a logged warning if ceiling approached
  - Document the threshold in `CLAUDE.md`
- [ ] Add configurable `MAX_CHUNKS` setting to the admin form (default: 10,000 for prod, 50,000 for dev)

### Ingestion Pipeline
- [ ] Add `--dry-run` flag to `run_pipeline.py` — runs all steps, skips write, reports what would be indexed
- [ ] Add `--verify` flag — loads existing index, runs chunk hash check, reports integrity status

### Docs
- [ ] Update `TOOLBOX.md` — manifest check, dry-run, verify commands
- [ ] Update `AGENTS.md` — corpus integrity owner: ingestion pipeline, not Drupal module
- [ ] Update `CLAUDE.md` — corpus trust model, memory ceiling rationale

**North Star checks:**
- Modularity? Corpus hash logic lives in ingestion pipeline, not Drupal. Admin display reads manifest only.
- No hacks? Memory ceiling is a configurable guard, not a silent truncation.
- Single responsibility? `store.py` writes, manifest is a separate post-write step.

---

## Sprint 6 — Production Deployment Path

**Branch:** `feature/sprint-6-production-deploy`
**Goal:** Make this deployable on a real government Drupal host. Secrets management, environment parity, deployment runbook.

### Secrets & Environment
- [ ] Document Azure Key Vault integration path — how to bind `DCPAS_OPENAI_API_KEY` from vault at runtime
- [ ] Add `settings.php` snippet for production secret injection (Drupal-standard pattern)
- [ ] Add `config/README.md` — never store real credentials in `config/install/` YML; documents env var precedence
- [ ] Add secrets-leak pre-commit hook: scan staged files for API key patterns before committing

### Deployment
- [ ] Write `DEPLOY.md` — step-by-step for:
  1. Module install on Drupal 10 host
  2. Ingestion pipeline first run
  3. Index verify pass
  4. Admin config walkthrough
  5. Smoke test (5 known questions → expected sources)
- [ ] Add `drush dcpas:healthcheck` command — verifies Azure connectivity, index presence, config validity
- [ ] Add `Makefile` with targets: `ingest`, `verify`, `healthcheck`, `test`, `lint`
- [ ] Add `.env.example` entries for all prod-relevant vars (already started, extend it)

### Accessibility & UX (for real users)
- [ ] Run `chatbot.js` and Twig template through WCAG 2.1 AA checklist:
  - ARIA roles on chat widget
  - Keyboard navigation (Enter to submit, Escape to close)
  - Screen reader announcement for new responses
  - Sufficient color contrast in `chatbot.css`
- [ ] Add language attribute to response output
- [ ] Add "Loading…" ARIA live region for spinner

### Performance Baseline
- [ ] Add response time logging to `ChatController` (total request time, retrieval time, Azure call time)
- [ ] Add `PERFORMANCE.md` — baseline numbers, acceptable thresholds, when to consider pgvector migration

### Docs
- [ ] `DEPLOY.md` — full deployment guide (created this sprint)
- [ ] Update `TOOLBOX.md` — Makefile targets, healthcheck, pre-commit hook
- [ ] Update `CLAUDE.md` — production secrets model, WCAG approach

**North Star checks:**
- No hacks? `drush healthcheck` tests real config, not mock state.
- Understandability? `DEPLOY.md` usable by a government Drupal admin with no Python background.
- Modularity? `healthcheck` is a separate Drush plugin, not folded into `ChatController`.

---

## Sprint 7 — Evaluation & Confidence Scoring

**Branch:** `feature/sprint-7-evaluation`
**Goal:** Give admins and developers tools to measure and improve retrieval quality over time.

### Evaluation Framework
- [ ] Build `tests/eval/` — small fixture set of 20+ known Q&A pairs mapped to expected source URLs
- [ ] Add `ingestion/evaluate.py` — runs eval fixtures against live index, reports:
  - Top-1 hit rate (was the right source in the top chunk?)
  - Top-3 hit rate
  - Average cosine similarity for correct retrievals
- [ ] Add eval step to CI — runs against index snapshot, fails if top-1 drops below threshold
- [ ] Document eval methodology in `AGENTS.md`

### Confidence Scoring
- [ ] Add minimum similarity threshold config (default: 0.70) to admin settings
- [ ] If best chunk score < threshold: return "I don't have enough information to answer that confidently" fallback
- [ ] Log low-confidence queries (hash only, no question text) for admin review

### Docs
- [ ] Update `TOOLBOX.md` — eval commands, interpreting results
- [ ] Update `AGENTS.md` — eval ownership, how to extend fixture set
- [ ] Update `CLAUDE.md` — confidence scoring design, fallback behavior rationale

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
