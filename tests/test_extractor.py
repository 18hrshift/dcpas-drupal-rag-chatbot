"""Tests for ingestion/extractor.py"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from ingestion.extractor import extract_html_text


class TestExtractHtmlText(unittest.TestCase):

    def test_extracts_title(self):
        html = '<html><head><title>My Page Title</title></head><body><p>Content.</p></body></html>'
        result = extract_html_text(html, 'https://example.com')
        self.assertEqual(result['title'], 'My Page Title')

    def test_extracts_body_text(self):
        html = '<html><body><p>Hello world.</p><p>Second paragraph.</p></body></html>'
        result = extract_html_text(html, 'https://example.com')
        self.assertIn('Hello world', result['text'])
        self.assertIn('Second paragraph', result['text'])

    def test_strips_script_tags(self):
        html = '<html><body><p>Good content.</p><script>alert("xss")</script></body></html>'
        result = extract_html_text(html, 'https://example.com')
        self.assertNotIn('alert', result['text'])
        self.assertIn('Good content', result['text'])

    def test_strips_style_tags(self):
        html = '<html><head><style>.foo { color: red; }</style></head><body><p>Text.</p></body></html>'
        result = extract_html_text(html, 'https://example.com')
        self.assertNotIn('color', result['text'])

    def test_strips_nav(self):
        html = '<html><body><nav><a href="/">Home</a></nav><main><p>Main content.</p></main></body></html>'
        result = extract_html_text(html, 'https://example.com')
        self.assertNotIn('Home', result['text'])
        self.assertIn('Main content', result['text'])

    def test_fallback_title_from_url(self):
        html = '<html><body><p>Content without title.</p></body></html>'
        result = extract_html_text(html, 'https://example.com/page')
        self.assertEqual(result['title'], 'https://example.com/page')

    def test_canonical_url_used(self):
        html = '''<html><head>
            <link rel="canonical" href="https://example.com/canonical-page"/>
        </head><body><p>Text</p></body></html>'''
        result = extract_html_text(html, 'https://example.com/original')
        self.assertEqual(result['url'], 'https://example.com/canonical-page')

    def test_source_url_fallback_when_no_canonical(self):
        html = '<html><body><p>Text</p></body></html>'
        result = extract_html_text(html, 'https://example.com/page')
        self.assertEqual(result['url'], 'https://example.com/page')

    def test_empty_html_returns_empty_text(self):
        result = extract_html_text('', 'https://example.com')
        self.assertEqual(result['text'], '')

    def test_returns_required_keys(self):
        result = extract_html_text('<p>Hi</p>', 'https://example.com')
        self.assertIn('url', result)
        self.assertIn('title', result)
        self.assertIn('text', result)

    def test_footer_stripped(self):
        html = '<html><body><article><p>Article text.</p></article><footer><p>Footer content.</p></footer></body></html>'
        result = extract_html_text(html, 'https://example.com')
        self.assertNotIn('Footer content', result['text'])
        self.assertIn('Article text', result['text'])


if __name__ == '__main__':
    unittest.main()
