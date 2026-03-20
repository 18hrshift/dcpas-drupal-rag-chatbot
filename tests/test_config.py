"""Tests for ingestion/config.py"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestLoadConfig(unittest.TestCase):

    def test_defaults_without_env(self):
        # Clear relevant env vars, then check defaults
        for key in ['OPENAI_API_KEY', 'OPENAI_API_BASE', 'OPENAI_API_VERSION',
                    'EMBEDDING_MODEL', 'CHAT_MODEL', 'TARGET_URL']:
            os.environ.pop(key, None)

        from ingestion.config import load_config
        config = load_config()

        self.assertIn('openai_api_key', config)
        self.assertEqual(config['openai_api_base'], 'https://api.openai.com/v1')
        self.assertEqual(config['embedding_model'], 'text-embedding-3-small')
        self.assertEqual(config['target_url'], 'https://dcpas.osd.mil')
        self.assertFalse(config['is_azure'])

    def test_azure_mode_detected_by_url(self):
        os.environ['OPENAI_API_BASE'] = 'https://myresource.openai.azure.com/openai'
        os.environ.pop('OPENAI_API_VERSION', None)

        from ingestion import config as cfg_module
        config = cfg_module.load_config()
        self.assertTrue(config['is_azure'])

        os.environ.pop('OPENAI_API_BASE', None)

    def test_azure_mode_detected_by_version(self):
        os.environ['OPENAI_API_VERSION'] = '2024-02-01'
        os.environ.pop('OPENAI_API_BASE', None)

        from ingestion import config as cfg_module
        config = cfg_module.load_config()
        self.assertTrue(config['is_azure'])

        os.environ.pop('OPENAI_API_VERSION', None)

    def test_env_file_loaded(self):
        # Write a temp .env and point load_config at it by putting it in project root
        # We test by injecting via os.environ directly (dotenv loading tested separately)
        os.environ['EMBEDDING_MODEL'] = 'text-embedding-ada-002'
        from ingestion import config as cfg_module
        config = cfg_module.load_config()
        self.assertEqual(config['embedding_model'], 'text-embedding-ada-002')
        os.environ.pop('EMBEDDING_MODEL', None)

    def test_trailing_slash_stripped_from_base(self):
        os.environ['OPENAI_API_BASE'] = 'https://api.openai.com/v1/'
        from ingestion import config as cfg_module
        config = cfg_module.load_config()
        self.assertFalse(config['openai_api_base'].endswith('/'))
        os.environ.pop('OPENAI_API_BASE', None)

    def test_max_pages_int(self):
        os.environ['MAX_PAGES'] = '250'
        from ingestion import config as cfg_module
        config = cfg_module.load_config()
        self.assertIsInstance(config['max_pages'], int)
        self.assertEqual(config['max_pages'], 250)
        os.environ.pop('MAX_PAGES', None)


if __name__ == '__main__':
    unittest.main()
