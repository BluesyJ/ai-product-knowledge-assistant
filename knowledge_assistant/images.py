from __future__ import annotations

import hashlib
import json
import re
import struct
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote

from .manifest import SourceDocument


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
IMAGE_RE = re.compile(
    r"!\[(?P<alt>(?:\\.|[^\]])*)\]\(\s*(?P<target><[^>]+>|[^\s)]+)(?:\s+['\"][^'\"]*['\"])?\s*\)"
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
CACHE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ImageReference:
    image_id: str
    source_id: str
    document_key: str
    document_title: str
    section: str
    line_number: int
    alt_text: str
    raw_target: str
    image_path: str
    relative_path: str
    exists: bool
    inside_source_root: bool
    image_sha256: str | None
    width: int | None
    height: int | None
    adjacent_before: str
    adjacent_after: str


@dataclass(frozen=True)
class ImageInventory:
    references: tuple[ImageReference, ...]
    missing: tuple[ImageReference, ...]
    unreferenced: tuple[str, ...]
    duplicate_hashes: dict[str, tuple[str, ...]]

    def to_dict(self) -> dict:
        return {
            "reference_count": len(self.references),
            "existing_reference_count": sum(item.exists for item in self.references),
            "missing_reference_count": len(self.missing),
            "unreferenced_count": len(self.unreferenced),
            "duplicate_content_group_count": len(self.duplicate_hashes),
            "references": [asdict(item) for item in self.references],
            "missing": [asdict(item) for item in self.missing],
            "unreferenced": list(self.unreferenced),
            "duplicate_hashes": {key: list(value) for key, value in self.duplicate_hashes.items()},
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def image_dimensions(path: Path) -> tuple[int | None, int | None]:
    """只读常见PNG/JPEG头部，避免为清单检查新增图像处理依赖。"""
    try:
        with path.open("rb") as handle:
            signature = handle.read(24)
            if signature.startswith(b"\x89PNG\r\n\x1a\n") and len(signature) >= 24:
                return struct.unpack(">II", signature[16:24])
            if signature[:2] != b"\xff\xd8":
                return None, None
            handle.seek(2)
            while True:
                marker_start = handle.read(1)
                if not marker_start:
                    break
                if marker_start != b"\xff":
                    continue
                marker = handle.read(1)
                while marker == b"\xff":
                    marker = handle.read(1)
                if marker in {b"\xd8", b"\xd9"}:
                    continue
                length_bytes = handle.read(2)
                if len(length_bytes) != 2:
                    break
                length = struct.unpack(">H", length_bytes)[0]
                if marker and marker[0] in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                    precision_height_width = handle.read(5)
                    if len(precision_height_width) == 5:
                        height, width = struct.unpack(">HH", precision_height_width[1:])
                        return width, height
                    break
                handle.seek(max(length - 2, 0), 1)
    except OSError:
        return None, None
    return None, None


def _line_sections(lines: list[str]) -> list[str]:
    heading_stack: list[str] = []
    sections: list[str] = []
    in_fence = False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            sections.append(" > ".join(heading_stack) if heading_stack else "文档导言")
            continue
        match = None if in_fence else HEADING_RE.match(line)
        if match:
            level = len(match.group(1))
            heading = match.group(2).strip().strip("*")
            if level == 1:
                heading_stack = []
            else:
                relative_level = max(level - 2, 0)
                heading_stack = heading_stack[:relative_level]
                heading_stack.append(heading)
        sections.append(" > ".join(heading_stack) if heading_stack else "文档导言")
    return sections


def _clean_context_line(line: str) -> str:
    if HEADING_RE.match(line) or IMAGE_RE.search(line):
        return ""
    return line.strip()


def _adjacent_context(lines: list[str], sections: list[str], index: int, direction: int) -> str:
    values: list[str] = []
    cursor = index + direction
    while 0 <= cursor < len(lines) and len(values) < 3:
        if sections[cursor] != sections[index]:
            break
        value = _clean_context_line(lines[cursor])
        if value:
            if direction < 0:
                values.insert(0, value)
            else:
                values.append(value)
        cursor += direction
    return "\n".join(values)


def _safe_resolve(source: SourceDocument, raw_target: str) -> tuple[Path, bool]:
    target = unquote(raw_target.strip().strip("<>")).replace("/", "\\")
    root = source.path.parent.resolve()
    resolved = (root / target).resolve()
    try:
        resolved.relative_to(root)
        return resolved, True
    except ValueError:
        return resolved, False


def inspect_source_images(source: SourceDocument) -> ImageInventory:
    if not source.include_images:
        return ImageInventory((), (), (), {})
    lines = source.path.read_text(encoding="utf-8").splitlines()
    sections = _line_sections(lines)
    references: list[ImageReference] = []
    referenced_paths: set[Path] = set()
    for index, line in enumerate(lines):
        for ordinal, match in enumerate(IMAGE_RE.finditer(line), start=1):
            raw_target = match.group("target")
            resolved, inside_root = _safe_resolve(source, raw_target)
            exists = inside_root and resolved.is_file()
            digest = sha256_file(resolved) if exists else None
            width, height = image_dimensions(resolved) if exists else (None, None)
            image_id_seed = f"{source.document_key}|{index + 1}|{ordinal}|{raw_target}"
            image_id = hashlib.sha256(image_id_seed.encode("utf-8")).hexdigest()[:20]
            relative_path = ""
            if inside_root:
                relative_path = resolved.relative_to(source.path.parent.resolve()).as_posix()
                referenced_paths.add(resolved)
            references.append(
                ImageReference(
                    image_id=image_id,
                    source_id=source.source_id,
                    document_key=source.document_key,
                    document_title=source.title,
                    section=sections[index],
                    line_number=index + 1,
                    alt_text=match.group("alt").replace("\\.", "."),
                    raw_target=raw_target,
                    image_path=str(resolved),
                    relative_path=relative_path,
                    exists=exists,
                    inside_source_root=inside_root,
                    image_sha256=digest,
                    width=width,
                    height=height,
                    adjacent_before=_adjacent_context(lines, sections, index, -1),
                    adjacent_after=_adjacent_context(lines, sections, index, 1),
                )
            )

    available = {
        path.resolve()
        for path in source.path.parent.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    }
    unreferenced = tuple(sorted(str(path) for path in available - referenced_paths))
    hashes: dict[str, list[str]] = {}
    for path in sorted(available):
        hashes.setdefault(sha256_file(path), []).append(str(path))
    duplicates = {key: tuple(value) for key, value in hashes.items() if len(value) > 1}
    missing = tuple(item for item in references if not item.exists)
    return ImageInventory(tuple(references), missing, unreferenced, duplicates)


def inspect_all_images(sources: Iterable[SourceDocument]) -> ImageInventory:
    references: list[ImageReference] = []
    missing: list[ImageReference] = []
    unreferenced: list[str] = []
    duplicates: dict[str, tuple[str, ...]] = {}
    for source in sources:
        report = inspect_source_images(source)
        references.extend(report.references)
        missing.extend(report.missing)
        unreferenced.extend(report.unreferenced)
        duplicates.update(report.duplicate_hashes)
    return ImageInventory(tuple(references), tuple(missing), tuple(unreferenced), duplicates)


def strip_image_references(markdown: str) -> str:
    """图片另建说明片段；正文切分时移除仅含路径的Markdown图片标记。"""
    return IMAGE_RE.sub("", markdown)


def load_image_cache(path: Path) -> dict:
    if not path.is_file():
        return {"schema_version": CACHE_SCHEMA_VERSION, "entries": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != CACHE_SCHEMA_VERSION or not isinstance(data.get("entries"), dict):
        raise ValueError(f"不支持的图片说明缓存格式：{path}")
    return data


def ensure_image_cache(inventory: ImageInventory, path: Path) -> dict:
    """以图片内容SHA-256为键；相同图片或重复入库不会重复调用视觉模型。"""
    cache = load_image_cache(path)
    entries = cache["entries"]
    now = datetime.now(timezone.utc).isoformat()
    for reference in inventory.references:
        if not reference.exists or not reference.image_sha256:
            continue
        entry = entries.setdefault(
            reference.image_sha256,
            {
                "status": "pending",
                "image_sha256": reference.image_sha256,
                "provider": None,
                "model": None,
                "generated_at": None,
                "visible_text": "",
                "summary": "",
                "structure": "",
                "relationships": "",
                "uncertainties": "",
                "error": None,
            },
        )
        entry["last_seen_at"] = now
        refs = entry.setdefault("references", [])
        ref_value = {
            "image_id": reference.image_id,
            "source_id": reference.source_id,
            "path": reference.image_path,
            "section": reference.section,
            "line_number": reference.line_number,
        }
        if ref_value not in refs:
            refs.append(ref_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return cache


def analyzed_description(entry: dict | None) -> str | None:
    if not entry or entry.get("status") != "analyzed":
        return None
    sections = ["[模型生成的图片说明，非原文]"]
    labels = (
        ("可见文字", "visible_text"),
        ("内容概述", "summary"),
        ("主要结构", "structure"),
        ("关键关系", "relationships"),
        ("不确定内容", "uncertainties"),
    )
    for label, key in labels:
        value = str(entry.get(key, "")).strip()
        if value:
            sections.append(f"{label}：{value}")
    return "\n".join(sections) if len(sections) > 1 else None


def write_image_inventory(inventory: ImageInventory, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(inventory.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

