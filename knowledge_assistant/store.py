from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Sequence

from qdrant_client import QdrantClient, models

from .config import COLLECTION_NAME, EXPECTED_VECTOR_SIZE, QDRANT_URL
from .preprocess import KnowledgeChunk


@dataclass(frozen=True)
class SearchResult:
    point_id: str
    score: float
    text: str
    payload: dict
    vector: list[float] | None = None


def make_client(url: str = QDRANT_URL, api_key: str | None = None, timeout: int = 30) -> QdrantClient:
    return QdrantClient(url=url, api_key=api_key or None, timeout=timeout)


def ensure_collection(
    client: QdrantClient,
    collection_name: str = COLLECTION_NAME,
    vector_size: int = EXPECTED_VECTOR_SIZE,
    create_indexes: bool = True,
) -> bool:
    """确保独立Collection存在；已有Collection配置不一致时停止，而不是覆盖。"""
    if client.collection_exists(collection_name):
        info = client.get_collection(collection_name)
        vectors = info.config.params.vectors
        actual_size = getattr(vectors, "size", None)
        actual_distance = getattr(vectors, "distance", None)
        if actual_size != vector_size or "cosine" not in str(actual_distance).lower():
            raise ValueError(
                f"Collection {collection_name} 配置不匹配："
                f"size={actual_size}, distance={actual_distance}"
            )
        return False

    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
    )
    if create_indexes:
        for field_name in ("document_key", "source_type", "content_type", "document_status"):
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=True,
            )
    return True


def field_filter(field_name: str, value: str) -> models.Filter:
    return models.Filter(
        must=[models.FieldCondition(key=field_name, match=models.MatchValue(value=value))]
    )


def _scroll_all(
    client: QdrantClient,
    collection_name: str,
    scroll_filter: models.Filter | None = None,
    with_vectors: bool = False,
) -> list:
    records: list = []
    offset = None
    while True:
        page, offset = client.scroll(
            collection_name=collection_name,
            scroll_filter=scroll_filter,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=with_vectors,
        )
        records.extend(page)
        if offset is None:
            break
    return records


def _document_is_current(existing: Sequence, chunks: Sequence[KnowledgeChunk]) -> bool:
    if len(existing) != len(chunks):
        return False
    expected_ids = {chunk.point_id for chunk in chunks}
    actual_ids = {str(item.id) for item in existing}
    if expected_ids != actual_ids:
        return False
    expected_hash = chunks[0].source_hash
    return all((item.payload or {}).get("source_hash") == expected_hash for item in existing)


def ingest_chunks(
    client: QdrantClient,
    embedder,
    chunks: Iterable[KnowledgeChunk],
    collection_name: str = COLLECTION_NAME,
    batch_size: int = 48,
) -> dict:
    """按文档比较哈希；未变化则跳过，变化时先删除该文档旧片段再写入。"""
    grouped: dict[str, list[KnowledgeChunk]] = defaultdict(list)
    for chunk in chunks:
        grouped[chunk.document_key].append(chunk)

    report = {
        "documents_total": len(grouped),
        "documents_updated": 0,
        "documents_unchanged": 0,
        "chunks_upserted": 0,
    }
    for document_key, document_chunks in grouped.items():
        document_chunks.sort(key=lambda item: item.chunk_index)
        condition = field_filter("document_key", document_key)
        existing = _scroll_all(client, collection_name, condition, with_vectors=False)
        if existing and _document_is_current(existing, document_chunks):
            report["documents_unchanged"] += 1
            continue
        if existing:
            client.delete(collection_name=collection_name, points_selector=condition, wait=True)

        for start in range(0, len(document_chunks), batch_size):
            batch = document_chunks[start : start + batch_size]
            vectors = embedder.embed_texts(chunk.embedding_text for chunk in batch)
            points = [
                models.PointStruct(id=chunk.point_id, vector=vector, payload=chunk.payload())
                for chunk, vector in zip(batch, vectors, strict=True)
            ]
            client.upsert(collection_name=collection_name, points=points, wait=True)
            report["chunks_upserted"] += len(points)
        report["documents_updated"] += 1
    return report


def search(
    client: QdrantClient,
    query_vector: Sequence[float],
    top_k: int = 5,
    collection_name: str = COLLECTION_NAME,
    source_type: str | None = None,
    with_vectors: bool = False,
) -> list[SearchResult]:
    query_filter = field_filter("source_type", source_type) if source_type else None
    response = client.query_points(
        collection_name=collection_name,
        query=list(query_vector),
        query_filter=query_filter,
        limit=top_k,
        with_payload=True,
        with_vectors=with_vectors,
    )
    results: list[SearchResult] = []
    for point in response.points:
        payload = dict(point.payload or {})
        vector = point.vector
        if isinstance(vector, dict):
            vector = next(iter(vector.values()), None)
        results.append(
            SearchResult(
                point_id=str(point.id),
                score=float(point.score),
                text=str(payload.get("text", "")),
                payload=payload,
                vector=list(vector) if vector is not None else None,
            )
        )
    return results


def document_chunks(
    client: QdrantClient,
    document_key: str,
    collection_name: str = COLLECTION_NAME,
    with_vectors: bool = True,
) -> list[SearchResult]:
    records = _scroll_all(
        client,
        collection_name,
        field_filter("document_key", document_key),
        with_vectors=with_vectors,
    )
    records.sort(key=lambda item: int((item.payload or {}).get("chunk_index", 0)))
    results: list[SearchResult] = []
    for item in records:
        payload = dict(item.payload or {})
        vector = item.vector
        if isinstance(vector, dict):
            vector = next(iter(vector.values()), None)
        results.append(
            SearchResult(
                point_id=str(item.id),
                score=0.0,
                text=str(payload.get("text", "")),
                payload=payload,
                vector=list(vector) if vector is not None else None,
            )
        )
    return results


def collection_count(client: QdrantClient, collection_name: str = COLLECTION_NAME) -> int:
    return int(client.count(collection_name=collection_name, exact=True).count)
