from __future__ import annotations

import unittest

from knowledge_assistant.manifest import SOURCES, validate_manifest
from knowledge_assistant.preprocess import build_corpus


class PreprocessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.chunks, cls.report = build_corpus()

    def test_manifest_has_expected_existing_sources(self) -> None:
        self.assertEqual(16, len(SOURCES))
        self.assertEqual([], validate_manifest())
        self.assertEqual(16, self.report.found_files)
        self.assertEqual(0, self.report.missing_files)

    def test_stable_ids_repeat(self) -> None:
        second, _ = build_corpus()
        self.assertEqual(
            [chunk.point_id for chunk in self.chunks],
            [chunk.point_id for chunk in second],
        )

    def test_faq_keeps_answer_and_boundary_together(self) -> None:
        matches = [
            chunk
            for chunk in self.chunks
            if chunk.source_id == "customer-objections-faq"
            and "直接识别图片" in chunk.section
        ]
        self.assertEqual(1, len(matches))
        self.assertIn("建议回答", matches[0].text)
        self.assertIn("回答边界", matches[0].text)
        self.assertEqual("faq", matches[0].content_type)

    def test_tables_keep_header(self) -> None:
        tables = [
            chunk
            for chunk in self.chunks
            if chunk.source_id == "managed-cloud" and chunk.content_type == "table"
        ]
        self.assertTrue(tables)
        self.assertTrue(any("| 顺序 | 脚本 | 写入行为 | 学习目标 |" in item.text for item in tables))

    def test_simulated_solutions_are_labeled(self) -> None:
        simulated = [chunk for chunk in self.chunks if chunk.source_type == "simulated_solution"]
        self.assertTrue(simulated)
        self.assertTrue(
            all(chunk.document_status == "simulated_scenario_not_customer_result" for chunk in simulated)
        )

    def test_placeholder_templates_are_not_in_manifest(self) -> None:
        paths = "\n".join(str(source.path) for source in SOURCES)
        self.assertNotIn("POC测试与验收报告模板", paths)
        self.assertNotIn("产品对比分析模板", paths)

    def test_trip_report_keeps_source_nature_and_is_not_qdrant_official(self) -> None:
        trip = next(source for source in SOURCES if source.source_id == "trip-report-bund-2026")
        self.assertEqual("ai_security", trip.product)
        self.assertEqual("trip_report", trip.source_type)
        self.assertTrue(trip.include_images)
        self.assertNotIn("official", trip.document_status)


if __name__ == "__main__":
    unittest.main()
