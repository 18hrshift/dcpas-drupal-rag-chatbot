"""Tests for ingestion/store.py"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.store import VectorStore


class TestVectorStore(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False)
        self.tmp.close()
        self.vs = VectorStore(self.tmp.name)

    def tearDown(self):
        self.vs.close()
        os.unlink(self.tmp.name)

    def _make_chunk(self, chunk_id='chunk_abc', source_url='https://x.com', text='Some text here.'):
        return {
            'chunk_id': chunk_id,
            'source_url': source_url,
            'title': 'Test Page',
            'chunk_index': 0,
            'text': text,
        }

    def test_empty_db_stats(self):
        stats = self.vs.stats()
        self.assertEqual(stats['pages'], 0)
        self.assertEqual(stats['chunks'], 0)
        self.assertEqual(stats['embedded'], 0)

    def test_upsert_chunk(self):
        chunk = self._make_chunk()
        self.vs.upsert_chunks([chunk])
        stats = self.vs.stats()
        self.assertEqual(stats['chunks'], 1)

    def test_chunk_exists(self):
        chunk = self._make_chunk()
        self.vs.upsert_chunks([chunk])
        self.assertTrue(self.vs.chunk_exists('chunk_abc'))
        self.assertFalse(self.vs.chunk_exists('nonexistent'))

    def test_upsert_idempotent(self):
        chunk = self._make_chunk()
        self.vs.upsert_chunks([chunk])
        self.vs.upsert_chunks([chunk])  # second insert should replace, not duplicate
        self.assertEqual(self.vs.stats()['chunks'], 1)

    def test_upsert_page(self):
        self.vs.upsert_page('https://x.com', 'X Page')
        self.assertEqual(self.vs.stats()['pages'], 1)

    def test_upsert_embeddings(self):
        chunk = self._make_chunk()
        chunk['embedding'] = [0.1, 0.2, 0.3]
        self.vs.upsert_chunks([chunk])
        self.vs.upsert_embeddings([chunk], model='text-embedding-3-small')
        self.assertTrue(self.vs.embedding_exists('chunk_abc'))
        self.assertEqual(self.vs.stats()['embedded'], 1)

    def test_embedding_not_exists(self):
        chunk = self._make_chunk()
        self.vs.upsert_chunks([chunk])
        self.assertFalse(self.vs.embedding_exists('chunk_abc'))

    def test_load_all_embeddings(self):
        chunk = self._make_chunk()
        chunk['embedding'] = [0.1, 0.2, 0.3]
        self.vs.upsert_chunks([chunk])
        self.vs.upsert_embeddings([chunk], model='test-model')
        rows = self.vs.load_all_embeddings()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['chunk_id'], 'chunk_abc')
        self.assertEqual(rows[0]['embedding'], [0.1, 0.2, 0.3])

    def test_load_all_embeddings_skips_none(self):
        # Chunks without embeddings should not appear in load_all_embeddings
        c1 = self._make_chunk('id1')
        c2 = self._make_chunk('id2')
        c2['embedding'] = [0.5, 0.5]
        self.vs.upsert_chunks([c1, c2])
        self.vs.upsert_embeddings([c1, c2], model='test')
        rows = self.vs.load_all_embeddings()
        ids = [r['chunk_id'] for r in rows]
        self.assertNotIn('id1', ids)  # c1 had no embedding
        self.assertIn('id2', ids)

    def test_multiple_chunks_same_page(self):
        chunks = [self._make_chunk(f'chunk_{i}', text=f'Text {i}') for i in range(5)]
        self.vs.upsert_chunks(chunks)
        self.assertEqual(self.vs.stats()['chunks'], 5)


if __name__ == '__main__':
    unittest.main()
