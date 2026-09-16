from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from knowledge_assistant.config import (
    COLLECTION_NAME,
    DEFAULT_CACHE_DIR,
    IMAGE_CACHE_PATH,
    IMAGE_INVENTORY_PATH,
    QDRANT_URL,
)
from knowledge_assistant.embedding import LocalEmbedder
from knowledge_assistant.images import ensure_image_cache, inspect_all_images, write_image_inventory
from knowledge_assistant.manifest import SOURCES, validate_manifest
from knowledge_assistant.preprocess import build_corpus, write_chunk_preview
from knowledge_assistant.store import ensure_collection, ingest_chunks, make_client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="预览或入库Qdrant产品知识Markdown")
    parser.add_argument("--preview-only", action="store_true", help="只切分和预览，不加载模型、不连接Qdrant")
    parser.add_argument("--preview-limit", type=int, default=18)
    parser.add_argument(
        "--preview-output",
        type=Path,
        default=Path(__file__).resolve().parent / "artifacts" / "chunk_preview.md",
    )
    parser.add_argument("--url", default=QDRANT_URL)
    parser.add_argument("--collection", default=COLLECTION_NAME)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--image-cache", type=Path, default=IMAGE_CACHE_PATH)
    parser.add_argument("--image-inventory", type=Path, default=IMAGE_INVENTORY_PATH)
    parser.add_argument(
        "--allow-model-download",
        action="store_true",
        help="允许FastEmbed下载缺失模型；默认关闭，避免静默下载大型资源",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    problems = validate_manifest()
    if problems:
        print(json.dumps({"manifest_errors": problems}, ensure_ascii=False, indent=2))
        return 2

    image_inventory = inspect_all_images(SOURCES)
    write_image_inventory(image_inventory, args.image_inventory)
    image_cache = ensure_image_cache(image_inventory, args.image_cache)
    print("图片清单统计：")
    print(
        json.dumps(
            {
                "references": len(image_inventory.references),
                "missing": len(image_inventory.missing),
                "unreferenced": len(image_inventory.unreferenced),
                "duplicate_content_groups": len(image_inventory.duplicate_hashes),
                "analyzed": sum(
                    entry.get("status") == "analyzed"
                    for entry in image_cache.get("entries", {}).values()
                ),
                "pending": sum(
                    entry.get("status") == "pending"
                    for entry in image_cache.get("entries", {}).values()
                ),
                "inventory_file": str(args.image_inventory),
                "description_cache": str(args.image_cache),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    chunks, report = build_corpus()
    write_chunk_preview(chunks, report, args.preview_output, limit=args.preview_limit)
    print("预处理统计：")
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    print(f"片段预览：{args.preview_output}")
    if args.preview_only:
        print("当前为preview-only：未加载Embedding、未连接或写入Qdrant。")
        return 0

    embedder = LocalEmbedder(cache_dir=args.cache_dir, allow_download=args.allow_model_download)
    print(f"Embedding模型：{embedder.model_name}；实际维度：{embedder.dimension}")
    api_key = os.getenv("QDRANT_KB_API_KEY") or None
    client = make_client(url=args.url, api_key=api_key)
    created = ensure_collection(
        client,
        collection_name=args.collection,
        vector_size=embedder.dimension,
    )
    ingest_report = ingest_chunks(
        client,
        embedder,
        chunks,
        collection_name=args.collection,
    )
    print("入库统计：")
    print(
        json.dumps(
            {
                "collection": args.collection,
                "collection_created": created,
                **ingest_report,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
