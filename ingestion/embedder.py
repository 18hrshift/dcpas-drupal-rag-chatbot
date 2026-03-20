"""
ingestion/embedder.py — Generate embeddings via OpenAI or Azure OpenAI API.

Sends chunk text to the embeddings endpoint in batches and returns float vectors.
Supports both standard OpenAI and Azure OpenAI — the correct endpoint is built
automatically from config (see config.py).

Usage:
  from ingestion.embedder import embed_chunks, embed_query
  chunks_with_vectors = embed_chunks(chunks, config)
  query_vector = embed_query("What is the pay scale?", config)
"""

import json
import time
import urllib.error
import urllib.request


# Max chunks per API request (OpenAI allows up to 2048 inputs per call,
# but smaller batches are more resumable and reduce timeout risk)
_BATCH_SIZE = 50

# Seconds to wait between batch requests to avoid rate limiting
_BATCH_DELAY = 0.5


def embed_chunks(chunks: list[dict], config: dict) -> list[dict]:
    """Add an 'embedding' key (list of floats) to each chunk dict.

    Processes chunks in batches. Chunks that fail are logged and returned
    with embedding=None so the pipeline can continue.

    Args:
        chunks: list of chunk dicts from chunker.chunk_document()
        config: pipeline config dict from config.load_config()

    Returns:
        The same list of dicts, each with an added 'embedding' field.
    """
    total = len(chunks)
    print(f"Embedding {total} chunks in batches of {_BATCH_SIZE}...")

    for batch_start in range(0, total, _BATCH_SIZE):
        batch = chunks[batch_start: batch_start + _BATCH_SIZE]
        # Truncate each chunk text; skip any that are somehow empty
        texts = [c["text"][:8000] for c in batch if c.get("text", "").strip()]
        if not texts:
            for chunk in batch:
                chunk["embedding"] = None
            continue

        try:
            vectors = _call_embeddings_api(texts, config)
        except Exception as e:
            print(f"  batch {batch_start}–{batch_start + len(batch)}: error — {e}")
            for chunk in batch:
                chunk["embedding"] = None
            time.sleep(_BATCH_DELAY * 4)
            continue

        for chunk, vector in zip(batch, vectors):
            chunk["embedding"] = vector

        done = min(batch_start + _BATCH_SIZE, total)
        print(f"  {done}/{total} chunks embedded")
        time.sleep(_BATCH_DELAY)

    return chunks


def embed_query(text: str, config: dict) -> list[float]:
    """Generate a single embedding vector for a query string.

    Args:
        text:   the query text to embed (max 8000 chars to stay within token limits)
        config: pipeline config dict

    Returns:
        Embedding vector as list of floats.

    Raises:
        ValueError if text is empty.
        RuntimeError on API failure.
    """
    if not text or not text.strip():
        raise ValueError("Cannot embed empty text.")
    # Truncate to avoid exceeding token limits (~8000 chars ≈ 2000 tokens)
    text = text[:8000]
    vectors = _call_embeddings_api([text], config)
    return vectors[0]


def _call_embeddings_api(texts: list[str], config: dict) -> list[list[float]]:
    """Call the OpenAI or Azure OpenAI embeddings endpoint.

    Args:
        texts:  list of strings to embed (one API call per batch)
        config: pipeline config dict

    Returns:
        List of embedding vectors in the same order as the input texts.

    Raises:
        RuntimeError on HTTP or network error.
    """
    url = _build_endpoint(config)
    api_key = config["openai_api_key"]
    model = config["embedding_model"]

    payload = {
        "input": texts,
        "model": model,
    }

    headers = {
        "Content-Type": "application/json",
    }

    # Azure uses api-key header; standard OpenAI uses Authorization Bearer
    if config.get("is_azure"):
        headers["api-key"] = api_key
    else:
        headers["Authorization"] = f"Bearer {api_key}"

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"Embeddings API HTTP {e.code}: {body_text}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Embeddings API network error: {e.reason}") from e

    # Sort by index to guarantee order matches input
    items = sorted(data["data"], key=lambda x: x["index"])
    return [item["embedding"] for item in items]


def _build_endpoint(config: dict) -> str:
    """Build the full embeddings API URL for OpenAI or Azure OpenAI."""
    base = config["openai_api_base"]
    model = config["embedding_model"]

    if config.get("is_azure"):
        # Azure: POST {base}/deployments/{deployment}/embeddings?api-version={version}
        version = config.get("openai_api_version", "2024-02-01")
        return f"{base}/deployments/{model}/embeddings?api-version={version}"
    else:
        # Standard OpenAI: POST https://api.openai.com/v1/embeddings
        return f"{base}/embeddings"
