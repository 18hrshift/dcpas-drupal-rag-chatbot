"""
ingestion/config.py — Configuration loader for the RAG ingestion pipeline.

Loads settings from .env file in the project root, falling back to environment
variables. Supports both standard OpenAI and Azure OpenAI endpoints.

Azure mode activates automatically when OPENAI_API_VERSION is set or when
OPENAI_API_BASE contains 'azure.com'.
"""

import os
from pathlib import Path


def load_config() -> dict:
    """Load configuration from .env file and environment variables.

    Returns a dict with all pipeline settings. Secrets never hardcoded —
    all values come from environment or .env file.
    """
    _load_dotenv()

    api_base = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
    api_version = os.environ.get("OPENAI_API_VERSION", "")
    is_azure = "azure.com" in api_base or bool(api_version)

    project_root = Path(__file__).parent.parent

    return {
        # API connectivity
        "openai_api_key": os.environ.get("OPENAI_API_KEY", ""),
        "openai_api_base": api_base,
        "openai_api_version": api_version,
        "is_azure": is_azure,

        # Model / deployment names
        # For Azure: these must match the deployment name in your Azure resource.
        # For standard OpenAI: these are model IDs (e.g. text-embedding-3-small).
        "embedding_model": os.environ.get("EMBEDDING_DEPLOYMENT") or os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
        "chat_model": os.environ.get("CHAT_DEPLOYMENT") or os.environ.get("CHAT_MODEL", "gpt-4o"),

        # Crawler settings
        "target_url": os.environ.get("TARGET_URL", "https://dcpas.osd.mil").rstrip("/"),
        "max_pages": int(os.environ.get("MAX_PAGES", "500")),
        "crawl_delay": float(os.environ.get("CRAWL_DELAY", "1.5")),

        # Local storage paths
        "db_path": str(project_root / os.environ.get("DB_PATH", "data/index.sqlite")),
        "pages_dir": str(project_root / os.environ.get("PAGES_DIR", "data/pages")),
        "pdfs_dir": str(project_root / os.environ.get("PDFS_DIR", "data/pdfs")),
    }


def _load_dotenv() -> None:
    """Load .env from project root into os.environ (does not overwrite existing vars)."""
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip optional surrounding quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            os.environ.setdefault(key, value)
