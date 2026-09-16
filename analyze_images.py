from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from knowledge_assistant.config import IMAGE_CACHE_PATH, IMAGE_INVENTORY_PATH
from knowledge_assistant.images import (
    ensure_image_cache,
    inspect_all_images,
    write_image_inventory,
)
from knowledge_assistant.manifest import SOURCES
from knowledge_assistant.vision import analyze_with_bailian_openai_compatible


DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查本地图文资料，或在明确授权后调用百炼生成图片说明")
    parser.add_argument("--execute", action="store_true", help="实际向百炼发送图片；默认仅更新本地清单和待解析缓存")
    parser.add_argument(
        "--confirm-external-upload",
        action="store_true",
        help="确认允许发送原图、文档标题、章节及相邻正文到配置的百炼服务",
    )
    parser.add_argument("--image-id", help="仅处理指定图片ID；默认处理全部待解析图片")
    parser.add_argument("--force", action="store_true", help="重新解析已经成功缓存的同内容图片")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = inspect_all_images(SOURCES)
    write_image_inventory(inventory, IMAGE_INVENTORY_PATH)
    cache = ensure_image_cache(inventory, IMAGE_CACHE_PATH)
    summary = {
        "references": len(inventory.references),
        "missing": len(inventory.missing),
        "unreferenced": len(inventory.unreferenced),
        "duplicate_content_groups": len(inventory.duplicate_hashes),
        "cache": str(IMAGE_CACHE_PATH),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.execute:
        print("当前仅完成本地清单和缓存初始化：没有读取图片内容，也没有向外部服务发送数据。")
        return 0
    if not args.confirm_external_upload:
        print("已阻止外部调用：--execute 必须同时提供 --confirm-external-upload。")
        return 2

    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    model = os.getenv("BAILIAN_VISION_MODEL", "")
    base_url = os.getenv("BAILIAN_VISION_BASE_URL", DEFAULT_BASE_URL)
    if not api_key or not model:
        print("缺少环境变量DASHSCOPE_API_KEY或BAILIAN_VISION_MODEL；未发送任何图片。")
        return 2

    entries = cache["entries"]
    processed = 0
    failed = 0
    for reference in inventory.references:
        if args.image_id and reference.image_id != args.image_id:
            continue
        if not reference.exists or not reference.image_sha256:
            continue
        entry = entries[reference.image_sha256]
        if entry.get("status") == "analyzed" and not args.force:
            continue
        try:
            result = analyze_with_bailian_openai_compatible(
                reference,
                api_key=api_key,
                model=model,
                base_url=base_url,
            )
            entry.update(
                {
                    "status": "analyzed",
                    "provider": "aliyun_bailian_openai_compatible",
                    "model": model,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "error": None,
                    **result,
                }
            )
            processed += 1
        except Exception as exc:
            entry.update(
                {
                    "status": "failed",
                    "provider": "aliyun_bailian_openai_compatible",
                    "model": model,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            failed += 1
        IMAGE_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"analyzed": processed, "failed": failed}, ensure_ascii=False, indent=2))
    print("说明缓存已更新。请再次执行 python ingest.py，才会把成功的图片说明写入Qdrant。")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

