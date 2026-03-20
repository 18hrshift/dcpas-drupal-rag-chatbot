"""Tests for ingestion/retrieve.py — uses a mocked embedder to avoid API calls."""

import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.store import VectorStore


# --- Pure cosine similarity helper (same logic as retrieve.py, tested independently) ---

def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x**2 for x in a))
    mag_b = math.sqrt(sum(x**2 for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


class TestCosineSimilarity(unittest.TestCase):

    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        self.assertAlmostEqual(cosine_similarity(v, v), 1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        self.assertAlmostEqual(cosine_similarity(a, b), 0.0)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        self.assertAlmostEqual(cosine_similarity(a, b), -1.0)

    def test_zero_vector_returns_zero(self):
        a = [0.0, 0.0]
        b = [1.0, 0.0]
        self.assertEqual(cosine_similarity(a, b), 0.0)

    def test_similar_vectors_high_score(self):
        a = [0.9, 0.1]
        b = [0.8, 0.2]
        score = cosine_similarity(a, b)
        self.assertGreater(score, 0.99)

    def test_length_mismatch_returns_zero(self):
        # retrieve.py handles this safely
        a = [1.0, 0.0]
        b = [1.0, 0.0, 0.0]
        # cosine_similarity(a, b) would be called with equal-length vectors in practice
        # but we verify the guard works
        from ingestion.retrieve import _cosine_similarity
        self.assertEqual(_cosine_similarity(a, b), 0.0)


class TestRetrieveIntegration(unittest.TestCase):
    """Integration test with a mocked embedder and a real SQLite store."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False)
        self.tmp.close()

        self.vs = VectorStore(self.tmp.name)

        # Seed the store with 3 chunks with known embedding vectors
        self.chunks = [
            {'chunk_id': 'chunk_a', 'source_url': 'https://x.com/pay',    'title': 'Pay Scales',   'chunk_index': 0, 'text': 'GS pay scale information', 'embedding': [1.0, 0.0, 0.0]},
            {'chunk_id': 'chunk_b', 'source_url': 'https://x.com/leave',  'title': 'Leave Policy', 'chunk_index': 0, 'text': 'Annual leave accrual',       'embedding': [0.0, 1.0, 0.0]},
            {'chunk_id': 'chunk_c', 'source_url': 'https://x.com/retire', 'title': 'Retirement',   'chunk_index': 0, 'text': 'FERS retirement benefits',   'embedding': [0.0, 0.0, 1.0]},
        ]
        self.vs.upsert_chunks(self.chunks)
        self.vs.upsert_embeddings(self.chunks, model='test')
        self.vs.close()

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_retrieves_most_similar_first(self):
        config = {
            'db_path': self.tmp.name,
            'openai_api_key': 'fake-key',
            'openai_api_base': 'https://api.openai.com/v1',
            'openai_api_version': '',
            'is_azure': False,
            'embedding_model': 'test',
        }
        # Query vector pointing toward chunk_a (pay scale)
        query_vector = [0.99, 0.01, 0.01]

        with patch('ingestion.retrieve.embed_query', return_value=query_vector):
            from ingestion.retrieve import retrieve
            results = retrieve('pay scale', config, top_k=3)

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]['chunk_id'], 'chunk_a')
        self.assertGreater(results[0]['score'], results[1]['score'])

    def test_top_k_limits_results(self):
        config = {
            'db_path': self.tmp.name,
            'openai_api_key': 'fake',
            'openai_api_base': 'https://api.openai.com/v1',
            'openai_api_version': '',
            'is_azure': False,
            'embedding_model': 'test',
        }
        with patch('ingestion.retrieve.embed_query', return_value=[1.0, 0.0, 0.0]):
            from ingestion.retrieve import retrieve
            results = retrieve('query', config, top_k=1)

        self.assertEqual(len(results), 1)

    def test_results_contain_required_keys(self):
        config = {
            'db_path': self.tmp.name,
            'openai_api_key': 'fake',
            'openai_api_base': 'https://api.openai.com/v1',
            'openai_api_version': '',
            'is_azure': False,
            'embedding_model': 'test',
        }
        with patch('ingestion.retrieve.embed_query', return_value=[1.0, 0.0, 0.0]):
            from ingestion.retrieve import retrieve
            results = retrieve('query', config, top_k=2)

        for r in results:
            self.assertIn('chunk_id', r)
            self.assertIn('source_url', r)
            self.assertIn('title', r)
            self.assertIn('text', r)
            self.assertIn('score', r)

    def test_empty_store_returns_empty(self):
        tmp2 = tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False)
        tmp2.close()
        VectorStore(tmp2.name).close()  # empty store

        config = {
            'db_path': tmp2.name,
            'openai_api_key': 'fake',
            'openai_api_base': 'https://api.openai.com/v1',
            'openai_api_version': '',
            'is_azure': False,
            'embedding_model': 'test',
        }
        with patch('ingestion.retrieve.embed_query', return_value=[1.0]):
            from ingestion.retrieve import retrieve
            results = retrieve('query', config, top_k=5)
        self.assertEqual(results, [])
        os.unlink(tmp2.name)


if __name__ == '__main__':
    unittest.main()
