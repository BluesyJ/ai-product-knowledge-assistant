from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QDRANT_URL = os.getenv("QDRANT_KB_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("QDRANT_KB_COLLECTION", "ai_product_kb_qdrant_v01")
EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
EXPECTED_VECTOR_SIZE = 512
DEFAULT_CACHE_DIR = Path(
    os.getenv(
        "FASTEMBED_CACHE_PATH",
        r"C:\Users\Administrator\AppData\Local\Temp\fastembed_cache",
    )
)
DEFAULT_CHUNK_CHARS = 1400
TABLE_ROWS_PER_CHUNK = 12
PRODUCT = "qdrant"
IMAGE_CACHE_PATH = PROJECT_ROOT / "artifacts" / "image_descriptions.json"
IMAGE_INVENTORY_PATH = PROJECT_ROOT / "artifacts" / "image_inventory.json"
