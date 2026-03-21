# PERFORMANCE.md — Response Time Baseline & Thresholds

> Baseline numbers will be populated after first production-equivalent load test.
> Update this file after each major deployment or configuration change.

---

## Request Pipeline Breakdown

Each chat request goes through these timed stages (logged to `dcpas_chatbot` channel):

| Stage | Variable | What it measures |
|-------|----------|-----------------|
| Retrieval | `retrieve_ms` | Embed query + cosine similarity over corpus |
| Azure call | `azure_ms` | HTTP roundtrip to OpenAI/Azure chat completions |
| Total | `total_ms` | Wall time from request entry to JSON response |

Log format (info level):
```
Chat processed. uid=1 ip=127.0.0.1 q_hash=abc123 chunks=5 total_ms=1842 retrieve_ms=340 azure_ms=1480
```

---

## Acceptable Thresholds (targets — not yet measured)

| Metric | Good | Acceptable | Action required |
|--------|------|-----------|----------------|
| `total_ms` | < 2 000 ms | < 4 000 ms | > 4 000 ms: investigate |
| `retrieve_ms` | < 500 ms | < 1 500 ms | > 1 500 ms: reduce `max_chunks` or migrate to pgvector |
| `azure_ms` | < 2 000 ms | < 3 500 ms | > 3 500 ms: check Azure region latency or increase timeout |

---

## Factors Affecting Retrieval Time

The in-process cosine similarity scan is O(n × d) where:
- `n` = number of chunks loaded (`max_chunks` setting)
- `d` = embedding dimensions (typically 1 536 for `text-embedding-3-small`)

Expected retrieval time at common corpus sizes (rough estimates — measure on actual hardware):

| `max_chunks` | Estimated `retrieve_ms` |
|-------------|------------------------|
| 1 000 | ~20–50 ms |
| 5 000 | ~100–200 ms |
| 10 000 | ~200–400 ms |
| 50 000 | ~1 000–2 000 ms |

If `retrieve_ms` consistently exceeds 1 500 ms at your corpus size, it is time
to migrate to pgvector (Sprint 8). See ROADMAP.md § Sprint 8.

---

## Reading Performance Logs

Using Drupal's database log (dblog):

```sql
-- Last 50 chat requests with timing
SELECT timestamp, message, variables
FROM watchdog
WHERE type = 'dcpas_chatbot' AND severity = 6
ORDER BY timestamp DESC
LIMIT 50;
```

Using shell (if logs are written to file):
```bash
grep 'Chat processed' /var/log/drupal/watchdog.log \
  | grep -oP 'total_ms=\K\d+' \
  | awk '{sum+=$1; n++} END {print "avg:", sum/n, "ms"}'
```

---

## When to Migrate to pgvector

Migrate to pgvector (Sprint 8) when **any** of the following are true:

1. `retrieve_ms` > 1 500 ms at your operational `max_chunks` setting
2. PHP memory ceiling warnings appear in logs (`VectorStore: memory ceiling reached`)
3. Corpus exceeds 50 000 chunks (hard `ABSOLUTE_ROW_CAP` in `VectorStore.php`)
4. Target host has PostgreSQL with the `pgvector` extension available

---

## Baseline (to be populated)

First production load test: **[date — not yet run]**

| Metric | p50 | p95 | p99 |
|--------|-----|-----|-----|
| `total_ms` | — | — | — |
| `retrieve_ms` | — | — | — |
| `azure_ms` | — | — | — |
| Corpus size | — chunks | | |
| PHP memory_limit | — MB | | |
| `max_chunks` setting | — | | |
