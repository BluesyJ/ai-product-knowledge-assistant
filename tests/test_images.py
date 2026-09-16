from __future__ import annotations

import json
import unittest
from pathlib import Path

from knowledge_assistant.images import ensure_image_cache, inspect_source_images
from knowledge_assistant.manifest import SOURCES
from knowledge_assistant.preprocess import chunks_for_source


class ImageTests(unittest.TestCase):
    def test_real_trip_report_has_complete_local_image_links(self) -> None:
        source = next(item for item in SOURCES if item.source_id == "trip-report-bund-2026")
        inventory = inspect_source_images(source)
        self.assertEqual(13, len(inventory.references))
        self.assertEqual(0, len(inventory.missing))
        self.assertEqual(0, len(inventory.unreferenced))
        self.assertEqual({}, inventory.duplicate_hashes)
        self.assertTrue(all(item.section != "文档导言" for item in inventory.references))

    def test_cache_uses_content_hash_and_analyzed_description_becomes_image_chunk(self) -> None:
        source = next(item for item in SOURCES if item.source_id == "trip-report-bund-2026")
        cache_path = Path(__file__).resolve().parents[1] / "artifacts" / ".test_image_cache.json"
        try:
            inventory = inspect_source_images(source)
            cache = ensure_image_cache(inventory, cache_path)
            digest = inventory.references[0].image_sha256
            cache["entries"][digest].update(
                {
                    "status": "analyzed",
                    "provider": "test-provider",
                    "model": "test-model",
                    "visible_text": "标题",
                    "summary": "一张结构示意图",
                    "structure": "左右布局",
                    "relationships": "左侧指向右侧",
                    "uncertainties": "小字无法确认",
                }
            )
            cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            chunks, _ = chunks_for_source(source, image_cache_path=cache_path)
            images = [chunk for chunk in chunks if chunk.content_type == "image_description"]
            self.assertEqual(1, len(images))
            self.assertEqual("image", images[0].asset_type)
            self.assertTrue(images[0].image_description_generated)
            self.assertIn("模型生成的图片说明", images[0].text)
            self.assertIn(inventory.references[0].section, images[0].embedding_text)
        finally:
            cache_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
