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

    # --- Sprint 5: corpus integrity ---

    def test_text_hash_stored(self):
        """upsert_chunks should store SHA-256 of chunk text."""
        import hashlib
        chunk = self._make_chunk(text='Verify me.')
        self.vs.upsert_chunks([chunk])
        row = self.vs._conn.execute(
            "SELECT text_hash FROM chunks WHERE chunk_id = ?", (chunk['chunk_id'],)
        ).fetchone()
        self.assertIsNotNone(row)
        expected = hashlib.sha256('Verify me.'.encode()).hexdigest()
        self.assertEqual(row[0], expected)

    def test_verify_hashes_all_ok(self):
        chunks = [self._make_chunk(f'h_{i}', text=f'Clean text {i}') for i in range(3)]
        self.vs.upsert_chunks(chunks)
        result = self.vs.verify_hashes()
        self.assertEqual(result['total'], 3)
        self.assertEqual(result['ok'], 3)
        self.assertEqual(result['mismatch'], 0)
        self.assertEqual(result['missing_hash'], 0)

    def test_verify_hashes_detects_mismatch(self):
        chunk = self._make_chunk(text='Original text.')
        self.vs.upsert_chunks([chunk])
        # Manually corrupt the stored hash
        self.vs._conn.execute(
            "UPDATE chunks SET text_hash = ? WHERE chunk_id = ?",
            ('badhash', chunk['chunk_id'])
        )
        self.vs._conn.commit()
        result = self.vs.verify_hashes()
        self.assertEqual(result['mismatch'], 1)
        self.assertEqual(result['ok'], 0)

    def test_corpus_hash_stable(self):
        chunks = [self._make_chunk(f'stable_{i}', text=f'Text {i}') for i in range(3)]
        self.vs.upsert_chunks(chunks)
        h1 = self.vs.corpus_hash()
        h2 = self.vs.corpus_hash()
        self.assertEqual(h1, h2)
        self.assertIsInstance(h1, str)
        self.assertEqual(len(h1), 64)  # SHA-256 hex

    def test_corpus_hash_changes_with_new_chunk(self):
        chunk = self._make_chunk('initial', text='Hello')
        self.vs.upsert_chunks([chunk])
        h1 = self.vs.corpus_hash()
        self.vs.upsert_chunks([self._make_chunk('added', text='World')])
        h2 = self.vs.corpus_hash()
        self.assertNotEqual(h1, h2)


if __name__ == '__main__':
    unittest.main()
