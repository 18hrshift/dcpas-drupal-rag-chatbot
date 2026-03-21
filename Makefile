# Makefile — DCPAS RAG Chatbot
# Run `make help` to see all targets.

PYTHON   ?= python3
DRUPAL   ?= /var/www/drupal
DRUSH    ?= $(DRUPAL)/vendor/bin/drush
PHPCS    ?= phpcs
ESLINT   ?= eslint

.PHONY: help ingest verify healthcheck test lint install-hooks eval

help:
	@echo ""
	@echo "DCPAS RAG Chatbot — available targets:"
	@echo ""
	@echo "  make ingest        Run full ingestion pipeline (crawl + embed)"
	@echo "  make embed         Embed only (skip crawl — use existing pages)"
	@echo "  make dry-run       Simulate embed without writing to the index"
	@echo "  make verify        Check corpus hash integrity and display manifest"
	@echo "  make stats         Print index statistics"
	@echo "  make healthcheck   Verify config, index, and API connectivity (requires Drush)"
	@echo "  make test          Run Python test suite"
	@echo "  make lint          Run PHP code style + JS lint checks"
	@echo "  make install-hooks Install git pre-commit secrets-leak hook"
	@echo "  make eval          Run retrieval evaluation (requires populated index)"
	@echo ""

ingest:
	$(PYTHON) ingestion/run_pipeline.py --crawl --embed

embed:
	$(PYTHON) ingestion/run_pipeline.py --embed

dry-run:
	$(PYTHON) ingestion/run_pipeline.py --dry-run --embed

verify:
	$(PYTHON) ingestion/run_pipeline.py --verify

stats:
	$(PYTHON) ingestion/run_pipeline.py --stats

healthcheck:
	$(DRUSH) dcpas:healthcheck

test:
	cd tests && $(PYTHON) -m pytest -v || $(PYTHON) -m unittest discover -v

lint:
	@echo "--- PHP code style ---"
	$(PHPCS) --standard=Drupal --extensions=php,module,install,yml \
	  drupal/dcpas_chatbot/src/ || true
	@echo "--- JS lint ---"
	$(ESLINT) drupal/dcpas_chatbot/js/chatbot.js || true

install-hooks:
	@echo "Installing pre-commit secrets-leak hook..."
	cp hooks/pre-commit .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit
	@echo "Done. Hook will scan staged files for API key patterns before each commit."

eval:
	$(PYTHON) ingestion/evaluate.py --verbose
