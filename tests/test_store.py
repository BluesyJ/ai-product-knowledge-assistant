from __future__ import annotations

import hashlib
import unittest
from dataclasses import replace

from qdrant_client import QdrantClient

from knowledge_assistant.preprocess import KnowledgeChunk
from knowledge_assistant.store import collection_count, ensure_collection, ingest_chunks, search


class FakeEmbedder:
    def embed_texts(self, texts):
        vectors = []
        for text in texts:
            if "技术" in text:
                vectors.append([1.0, 0.0, 0.0])
            elif "模拟" in text:
                vectors.append([0.8, 0.6, 0.0])
            else:
                vectors.append([0.0, 1.0, 0.0])
        return vectors


def make_chunk(point_id: str, source_id: str, source_type: str, text: str) -> KnowledgeChunk:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return KnowledgeChunk(
        point_id=point_id,
        stable_id=f"qdrant|{source_id}|section|0001",
        document_key=f"qdrant|{source_id}",
        source_id=source_id,
        product="qdrant",
        document_title=source_id,
        section="测试章节",
        source_file=f"D:/example/{source_id}.md",
        source_type=source_type,
        document_status="test",
        known_date=None,
        source_urls=(),
        content_type="section",
        chunk_index=0,
        text=text,
        embedding_text=text,
        source_hash=digest,
        content_hash=digest,
    )


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = QdrantClient(location=":memory:")
        self.collection = "kb_test"
        ensure_collection(self.client, self.collection, vector_size=3, create_indexes=False)
        self.embedder = FakeEmbedder()
        self.chunks = [
            make_chunk("79ca290d-6ca9-50e1-a7fd-62c42a38a442", "tech", "technical_note", "技术过滤说明"),
            make_chunk("727ed218-0fb8-50d8-af99-6050c2df9fc0", "scenario", "simulated_solution", "模拟客户方案"),
        ]

    def test_repeat_ingest_is_idempotent(self) -> None:
        first = ingest_chunks(self.client, self.embedder, self.chunks, self.collection)
        second = ingest_chunks(self.client, self.embedder, self.chunks, self.collection)
        self.assertEqual(2, first["documents_updated"])
        self.assertEqual(2, second["documents_unchanged"])
        self.assertEqual(2, collection_count(self.client, self.collection))

    def test_changed_document_replaces_old_payload(self) -> None:
        ingest_chunks(self.client, self.embedder, self.chunks, self.collection)
        changed_text = "技术过滤说明已经更新"
        changed_hash = hashlib.sha256(changed_text.encode("utf-8")).hexdigest()
        changed = replace(
            self.chunks[0],
            text=changed_text,
            embedding_text=changed_text,
            source_hash=changed_hash,
            content_hash=changed_hash,
        )
        report = ingest_chunks(self.client, self.embedder, [changed, self.chunks[1]], self.collection)
        self.assertEqual(1, report["documents_updated"])
        self.assertEqual(1, report["documents_unchanged"])
        result = search(self.client, [1.0, 0.0, 0.0], 2, self.collection)[0]
        self.assertEqual(changed_text, result.text)

    def test_source_type_filter_changes_candidate_set(self) -> None:
        ingest_chunks(self.client, self.embedder, self.chunks, self.collection)
        unfiltered = search(self.client, [1.0, 0.0, 0.0], 2, self.collection)
        filtered = search(
            self.client,
            [1.0, 0.0, 0.0],
            2,
            self.collection,
            source_type="simulated_solution",
        )
        self.assertEqual(2, len(unfiltered))
        self.assertEqual(1, len(filtered))
        self.assertEqual("simulated_solution", filtered[0].payload["source_type"])


if __name__ == "__main__":
    unittest.main()
