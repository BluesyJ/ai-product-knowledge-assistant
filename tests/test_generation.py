from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import httpx
from openai import OpenAI

from knowledge_assistant.generation import (
    build_context,
    generate_with_truefoundry,
    parse_routing_headers,
    remove_invalid_citations,
)
from knowledge_assistant.store import SearchResult


class GenerationTests(unittest.TestCase):
    def test_context_uses_real_result_order(self) -> None:
        results = [
            SearchResult(
                point_id="1",
                score=0.9,
                text="第一段正文",
                payload={
                    "document_title": "文档A",
                    "section": "章节A",
                    "source_type": "internal_faq",
                    "document_status": "draft",
                },
            ),
            SearchResult(
                point_id="2",
                score=0.8,
                text="第二段正文",
                payload={
                    "document_title": "文档B",
                    "section": "章节B",
                    "source_type": "experiment_record",
                    "document_status": "historical",
                },
            ),
        ]
        context = build_context(results)
        self.assertIn("[1] 文档：文档A", context)
        self.assertIn("[2] 文档：文档B", context)

    def test_invalid_citations_are_removed(self) -> None:
        cleaned, invalid = remove_invalid_citations("结论[1]，另一结论[9]。", source_count=2)
        self.assertEqual("结论[1]，另一结论。", cleaned)
        self.assertEqual((9,), invalid)

    def test_auto_routing_headers_are_parsed(self) -> None:
        headers = {
            "x-tfy-resolved-model": "provider/model-a",
            "x-tfy-applied-rules": (
                '{"complexity":{"tier":"medium","cause":"heuristic"},'
                '"routing_model_order":["provider/model-a"]}'
            ),
        }
        routing = parse_routing_headers(headers)
        self.assertEqual("provider/model-a", routing.resolved_model)
        self.assertEqual("medium", routing.route_tier)
        self.assertEqual("heuristic", routing.route_cause)

    def test_missing_routing_headers_remain_unknown(self) -> None:
        routing = parse_routing_headers({})
        self.assertIsNone(routing.resolved_model)
        self.assertIsNone(routing.route_tier)
        self.assertIsNone(routing.route_cause)

    def test_streaming_auto_routing_response_is_consumed(self) -> None:
        captured_request: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_request.update(json.loads(request.content.decode("utf-8")))
            body = (
                'data: {"id":"chunk-1","object":"chat.completion.chunk","created":0,'
                '"model":"provider/model-a","choices":[{"index":0,'
                '"delta":{"content":"回答[1]"},"finish_reason":null}]}\n\n'
                'data: {"id":"chunk-2","object":"chat.completion.chunk","created":0,'
                '"model":"provider/model-a","choices":[{"index":0,"delta":{},'
                '"finish_reason":"stop"}],"usage":{"prompt_tokens":12,'
                '"completion_tokens":3,"total_tokens":15}}\n\n'
                "data: [DONE]\n\n"
            )
            return httpx.Response(
                200,
                headers={
                    "content-type": "text/event-stream",
                    "x-tfy-resolved-model": "provider/model-a",
                    "x-tfy-applied-rules": (
                        '{"complexity":{"tier":"medium","cause":"heuristic"}}'
                    ),
                },
                content=body.encode("utf-8"),
            )

        def make_client(**_: object) -> OpenAI:
            return OpenAI(
                api_key="offline-test-token",
                base_url="https://offline.test",
                http_client=httpx.Client(transport=httpx.MockTransport(handler)),
            )

        partials: list[str] = []
        with patch("openai.OpenAI", side_effect=make_client):
            answer = generate_with_truefoundry(
                "测试问题",
                [
                    SearchResult(
                        point_id="1",
                        score=0.9,
                        text="测试资料",
                        payload={
                            "document_title": "文档A",
                            "section": "章节A",
                            "source_type": "internal_faq",
                            "document_status": "draft",
                        },
                    )
                ],
                token="hidden-at-runtime",
                model="qdrant-truefoundry-demo/qdrant-truefoundry-demo",
                on_text=partials.append,
            )

        self.assertTrue(captured_request["stream"])
        self.assertEqual(
            "qdrant-truefoundry-demo/qdrant-truefoundry-demo",
            captured_request["model"],
        )
        self.assertEqual("回答[1]", answer.text)
        self.assertEqual(["回答[1]"], partials)
        self.assertEqual("provider/model-a", answer.resolved_model)
        self.assertEqual("medium", answer.route_tier)
        self.assertEqual("heuristic", answer.route_cause)
        self.assertEqual(15, answer.total_tokens)


if __name__ == "__main__":
    unittest.main()
