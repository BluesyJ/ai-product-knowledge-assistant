from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceDocument:
    source_id: str
    path: Path
    title: str
    source_type: str
    document_status: str
    known_date: str | None = None
    source_urls: tuple[str, ...] = ()
    product: str = "qdrant"
    include_images: bool = False

    @property
    def document_key(self) -> str:
        return f"{self.product}|{self.source_id}"


# 清单是第一版知识范围的唯一入口。新文件不会因为放进目录而自动入库。
SOURCES: tuple[SourceDocument, ...] = (
    SourceDocument(
        "presales-playbook",
        Path(r"D:\SYJProject\HongKe\Qdrant\docs\QDRANT_PRESALES_PLAYBOOK.md"),
        "Qdrant 售前手册：定位、需求访谈、演示与常见问题",
        "internal_presales",
        "recommended_internal_entry_review_pending",
        "2026-08-20",
    ),
    SourceDocument(
        "customer-objections-faq",
        Path(r"D:\SYJProject\HongKe\Qdrant\docs\QDRANT_CUSTOMER_OBJECTIONS_FAQ.md"),
        "Qdrant 常见客户异议及应对 FAQ",
        "internal_faq",
        "reusable_draft_non_contractual",
        "2026-08-26",
    ),
    SourceDocument(
        "advanced-filter-learning",
        Path(r"D:\SYJProject\HongKe\Qdrant\docs\ADVANCED_FILTER_LEARNING.md"),
        "复杂过滤、分页与排序学习笔记",
        "technical_note",
        "internal_learning_note_review_pending",
        "2026-08-14",
    ),
    SourceDocument(
        "query-api-learning",
        Path(r"D:\SYJProject\HongKe\Qdrant\docs\QUERY_API_LEARNING.md"),
        "Query API 第二阶段学习笔记",
        "technical_note",
        "internal_learning_note_with_regression_reference",
        "2026-08-14",
    ),
    SourceDocument(
        "collection-lifecycle",
        Path(r"D:\SYJProject\HongKe\Qdrant\experiments\04_collection_lifecycle\README.md"),
        "Collection 生命周期与业务发布",
        "experiment_guide",
        "code_and_guide_exist_rerun_required",
    ),
    SourceDocument(
        "cluster-operations",
        Path(r"D:\SYJProject\HongKe\Qdrant\experiments\05_cluster_operations\README.md"),
        "集群、可靠性与运维",
        "experiment_guide",
        "three_node_guide_not_production_commitment",
    ),
    SourceDocument(
        "managed-cloud",
        Path(r"D:\SYJProject\HongKe\Qdrant\experiments\06_managed_cloud\README.md"),
        "Qdrant Managed Cloud",
        "experiment_guide",
        "historical_cloud_learning_plan_dependent",
        "2026-08-17",
        ("https://qdrant.tech/documentation/cloud/",),
    ),
    SourceDocument(
        "glossary",
        Path(r"D:\虹科\云文档\Qdrant\技术文档\术语汇总.md"),
        "Qdrant 术语汇总",
        "cloud_doc_export",
        "partial_internal_note_review_pending",
    ),
    SourceDocument(
        "hnsw-explainer",
        Path(r"D:\虹科\云文档\Qdrant\技术文档\算法详解\HNSW算法.md"),
        "HNSW 算法",
        "technical_explainer",
        "internal_explainer_review_pending",
    ),
    SourceDocument(
        "snapshot-lab",
        Path(r"D:\虹科\云文档\Qdrant\技术文档\本地代码测试\4.4 snapshot技术说明与实验手册.md"),
        "Snapshot 技术说明与实验手册",
        "experiment_record",
        "historical_learning_validation_not_dr_commitment",
        source_urls=(
            "https://qdrant.tech/documentation/concepts/snapshots/",
            "https://qdrant.tech/documentation/tutorials-operations/create-snapshot/",
        ),
    ),
    SourceDocument(
        "hnsw-benchmark",
        Path(r"D:\虹科\云文档\Qdrant\技术文档\本地代码测试\4.5 HNSW 参数、Recall@K 与查询延迟对比实验.md"),
        "HNSW 参数、Recall@K 与查询延迟对比实验",
        "experiment_record",
        "historical_local_result_conditions_apply",
    ),
    SourceDocument(
        "quantization-storage",
        Path(r"D:\虹科\云文档\Qdrant\技术文档\本地代码测试\4.8 量化与存储优化测试.md"),
        "量化与存储优化测试",
        "experiment_record",
        "concept_and_selection_note_numeric_evidence_not_embedded",
        source_urls=("https://qdrant.tech/documentation/guides/quantization/",),
    ),
    SourceDocument(
        "simulated-bank-rag",
        Path(r"D:\虹科\云文档\Qdrant\解决方案\“跨国银行中国区数据不出域”RAG检索基座解决方案.md"),
        "跨国银行中国区数据不出域 RAG 检索基座解决方案",
        "simulated_solution",
        "simulated_scenario_not_customer_result",
    ),
    SourceDocument(
        "simulated-manufacturing-multimodal",
        Path(r"D:\虹科\云文档\Qdrant\解决方案\“制造业质量缺陷”多模态相似案例检索分析方案.md"),
        "制造业质量缺陷多模态相似案例检索分析方案",
        "simulated_solution",
        "simulated_scenario_not_customer_result",
    ),
    SourceDocument(
        "reviews-case-analysis",
        Path(r"D:\SYJProject\HongKe\Qdrant\docs\marketing\艾体宝_Qdrant案例解读_27亿条评论向量背后.md"),
        "27亿条评论向量背后的Qdrant案例解读",
        "marketing_case_analysis",
        "local_article_user_confirmed_published_not_customer_result",
        "2026-09-04",
        (
            "https://qdrant.tech/blog/case-study-bazaarvoice/",
            "https://qdrant.tech/documentation/concepts/filtering/",
            "https://qdrant.tech/documentation/guides/quantization/",
        ),
    ),
    SourceDocument(
        "trip-report-bund-2026",
        Path(r"D:\虹科\云文档\出差报告\2026外滩大会.md"),
        "2026外滩大会出差报告",
        "trip_report",
        "personal_trip_report_meeting_notes_and_vendor_presentations",
        "2026-09-09",
        product="ai_security",
        include_images=True,
    ),
)


def source_by_id(source_id: str) -> SourceDocument:
    for source in SOURCES:
        if source.source_id == source_id:
            return source
    raise KeyError(f"未知来源：{source_id}")


def validate_manifest() -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for source in SOURCES:
        if source.source_id in seen:
            problems.append(f"重复 source_id：{source.source_id}")
        seen.add(source.source_id)
        if not source.path.is_file():
            problems.append(f"文件不存在：{source.path}")
    return problems
