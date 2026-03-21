# Contributing to DCPAS RAG Chatbot

## Branch Model

```
main          ← production-ready, tagged releases only
develop       ← integration branch, all PRs merge here first
feature/*     ← new capabilities
fix/*         ← bug fixes and security patches
docs/*        ← documentation-only changes
chore/*       ← tooling, deps, config
```

## Commit Format

```
<type>(<scope>): <short summary>

Types:  feat | fix | docs | test | chore | refactor | security
Scopes: drupal | ingestion | pipeline | config | tests | ci
```

Examples:
```
security(drupal): harden prompt injection filter — expand blocklist
feat(ingestion): add corpus integrity hash check on index write
docs(all): update TOOLBOX, CLAUDE, AGENTS for Sprint 4
fix(drupal): replace innerHTML spinner with programmatic DOM build
```

## Pull Request Rules

- Every PR targets `develop`, not `main`.
- PR description must include: **What**, **Why**, **Security impact** (none / mitigated / new).
- No force-pushes to `main` or `develop`.
- Squash-merge from `feature/*` and `fix/*` to keep history readable.
- `main` merges are tagged (`v0.x.0`) with a release note.

## Running Tests Locally

```bash
# Python tests
cd tests/
python3 -m pytest -v

# PHP code style (requires phpcs + Drupal coding standards)
phpcs --standard=Drupal drupal/dcpas_chatbot/src/

# JS lint
eslint drupal/dcpas_chatbot/js/chatbot.js
```

## Security Policy

See [SECURITY.md](SECURITY.md) for the threat model, known limitations, and
responsible disclosure process.
