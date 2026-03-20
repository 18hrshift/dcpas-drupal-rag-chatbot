"""Tests for ingestion/chunker.py"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from ingestion.chunker import chunk_document, CHUNK_SIZE_WORDS, OVERLAP_WORDS


class TestChunkDocument(unittest.TestCase):

    def test_empty_text_returns_empty(self):
        self.assertEqual(chunk_document("https://example.com", "Title", ""), [])

    def test_whitespace_only_returns_empty(self):
        self.assertEqual(chunk_document("https://example.com", "Title", "   \n\t  "), [])

    def test_short_text_single_chunk(self):
        text = "This is a short document with fewer words than the chunk size limit."
        chunks = chunk_document("https://example.com/page", "My Page", text)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["source_url"], "https://example.com/page")
        self.assertEqual(chunks[0]["title"], "My Page")
        self.assertEqual(chunks[0]["chunk_index"], 0)
        self.assertIn("chunk_id", chunks[0])

    def test_long_text_multiple_chunks(self):
        # Generate text that is definitely longer than one chunk
        words = ["word"] * (CHUNK_SIZE_WORDS * 3)
        text = " ".join(words)
        chunks = chunk_document("https://example.com", "Long Doc", text)
        self.assertGreater(len(chunks), 1)

    def test_overlap_means_shared_words(self):
        # Adjacent chunks should share some words due to overlap
        words = ["word{}".format(i) for i in range(CHUNK_SIZE_WORDS * 2)]
        text = " ".join(words)
        chunks = chunk_document("https://example.com", "Test", text)
        if len(chunks) >= 2:
            end_of_first = chunks[0]["text"].split()[-OVERLAP_WORDS:]
            start_of_second = chunks[1]["text"].split()[:OVERLAP_WORDS]
            self.assertEqual(end_of_first, start_of_second)

    def test_chunk_ids_are_stable(self):
        text = "Some stable content here."
        c1 = chunk_document("https://example.com", "T", text)
        c2 = chunk_document("https://example.com", "T", text)
        self.assertEqual(c1[0]["chunk_id"], c2[0]["chunk_id"])

    def test_different_urls_different_ids(self):
        text = "Same content."
        c1 = chunk_document("https://example.com/a", "T", text)
        c2 = chunk_document("https://example.com/b", "T", text)
        self.assertNotEqual(c1[0]["chunk_id"], c2[0]["chunk_id"])

    def test_chunk_indices_sequential(self):
        words = ["w"] * (CHUNK_SIZE_WORDS * 3)
        chunks = chunk_document("https://x.com", "T", " ".join(words))
        indices = [c["chunk_index"] for c in chunks]
        self.assertEqual(indices, list(range(len(chunks))))

    def test_chunk_text_is_string(self):
        chunks = chunk_document("https://x.com", "T", "Hello world test.")
        self.assertIsInstance(chunks[0]["text"], str)
        self.assertTrue(chunks[0]["text"].strip())


class TestChunkSize(unittest.TestCase):

    def test_chunk_words_not_exceed_limit(self):
        words = ["word"] * (CHUNK_SIZE_WORDS * 4)
        chunks = chunk_document("https://x.com", "T", " ".join(words))
        for chunk in chunks:
            word_count = len(chunk["text"].split())
            self.assertLessEqual(word_count, CHUNK_SIZE_WORDS,
                                 f"Chunk {chunk['chunk_index']} has {word_count} words, expected <= {CHUNK_SIZE_WORDS}")


if __name__ == '__main__':
    unittest.main()
