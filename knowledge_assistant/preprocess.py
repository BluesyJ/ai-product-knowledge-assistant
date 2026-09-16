from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .config import DEFAULT_CHUNK_CHARS, IMAGE_CACHE_PATH, TABLE_ROWS_PER_CHUNK
from .images import analyzed_description, inspect_source_images, load_image_cache, strip_image_references
from .manifest import SOURCES, SourceDocument


CHUNK_NAMESPACE = uuid.UUID("4f42b1b0-27e6-4acd-a77a-7715f5f0a8af")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


@dataclass(frozen=True)
class MarkdownSection:
    heading_level: int
    heading_path: tuple[str, ...]
    body: str

    @property
    def section_path(self) -> str:
        return " > ".join(self.heading_path) if self.heading_path else "文档导言"


@dataclass(frozen=True)
class KnowledgeChunk:
    point_id: str
    stable_id: str
    document_key: str
    source_id: str
    product: str
    document_title: str
    section: str
    source_file: str
    source_type: str
    document_status: str
    known_date: str | None
    source_urls: tuple[str, ...]
    content_type: str
    chunk_index: int
    text: str
    embedding_text: str
    source_hash: str
    content_hash: str
    asset_type: str = "text"
    image_id: str | None = None
    image_path: str | None = None
    image_sha256: str | None = None
    image_alt_text: str | None = None
    image_adjacent_before: str | None = None
    image_adjacent_after: str | None = None
    image_description_generated: bool = False
    image_description_provider: str | None = None
    image_description_model: str | None = None

    def payload(self) -> dict:
        payload = asdict(self)
        payload.pop("embedding_text")
        payload["source_urls"] = list(self.source_urls)
        return payload


@dataclass
class BuildReport:
    configured_files: int = 0
    found_files: int = 0
    missing_files: int = 0
    generated_chunks: int = 0
    kept_chunks: int = 0
    duplicate_chunks: int = 0
    empty_sections: int = 0
    missing_paths: list[str] | None = None
    skipped: list[dict] | None = None

    def __post_init__(self) -> None:
        self.missing_paths = [] if self.missing_paths is None else self.missing_paths
        self.skipped = [] if self.skipped is None else self.skipped

    def to_dict(self) -> dict:
        data = asdict(self)
        data["skipped_reason_counts"] = {
            "missing_file": self.missing_files,
            "empty_or_too_short_section": self.empty_sections,
            "duplicate_chunk": self.duplicate_chunks,
        }
        return data


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_markdown(text: str) -> str:
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def normalized_content_key(text: str) -> str:
    # 仅用于发现重复片段；不改写最终展示的原文。
    normalized = re.sub(r"\s+", "", text).replace("\\-", "-").replace("\\.", ".")
    return sha256_text(normalized)


def parse_markdown_sections(text: str) -> tuple[str | None, list[MarkdownSection]]:
    """按Markdown标题建立层级。代码块中的#不会被误判为标题。"""
    document_title: str | None = None
    heading_stack: list[str] = []
    sections: list[MarkdownSection] = []
    current_lines: list[str] = []
    current_level = 1
    in_fence = False

    def flush() -> None:
        nonlocal current_lines
        body = "\n".join(current_lines).strip()
        if body:
            sections.append(MarkdownSection(current_level, tuple(heading_stack), body))
        current_lines = []

    for line in normalize_markdown(text).splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            current_lines.append(line)
            continue
        match = None if in_fence else HEADING_RE.match(line)
        if not match:
            current_lines.append(line)
            continue
        flush()
        level = len(match.group(1))
        heading = match.group(2).strip().strip("*")
        if level == 1 and document_title is None:
            document_title = heading
            heading_stack = []
        else:
            relative_level = max(level - 2, 0)
            heading_stack = heading_stack[:relative_level]
            heading_stack.append(heading)
        current_level = level
    flush()
    return document_title, sections


def _is_table_start(lines: Sequence[str], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and "|" in lines[index]
        and bool(TABLE_SEPARATOR_RE.match(lines[index + 1]))
    )


def split_markdown_blocks(body: str) -> list[str]:
    """把表格和代码围栏作为原子块，避免在中间切断结构。"""
    lines = body.splitlines()
    blocks: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            text = "\n".join(paragraph).strip()
            if text:
                blocks.append(text)
            paragraph.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        if line.lstrip().startswith("```"):
            flush_paragraph()
            fenced = [line]
            index += 1
            while index < len(lines):
                fenced.append(lines[index])
                if lines[index].lstrip().startswith("```"):
                    index += 1
                    break
                index += 1
            blocks.append("\n".join(fenced).strip())
            continue
        if _is_table_start(lines, index):
            flush_paragraph()
            table = [lines[index], lines[index + 1]]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                table.append(lines[index])
                index += 1
            blocks.append("\n".join(table).strip())
            continue
        if not line.strip():
            flush_paragraph()
        else:
            paragraph.append(line)
        index += 1
    flush_paragraph()
    return blocks


def split_table(table: str, rows_per_chunk: int = TABLE_ROWS_PER_CHUNK) -> list[str]:
    lines = table.splitlines()
    if len(lines) <= rows_per_chunk + 2:
        return [table]
    header = lines[:2]
    rows = lines[2:]
    return ["\n".join(header + rows[i : i + rows_per_chunk]) for i in range(0, len(rows), rows_per_chunk)]


def split_long_prose(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    # 中文标点后通常没有空格，因此保留标点进行切分。
    sentences = [part.strip() for part in re.findall(r".*?(?:[。！？；]|$)", text, flags=re.S) if part.strip()]
    if len(sentences) <= 1:
        return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]
    parts: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > max_chars:
            parts.append(current.strip())
            current = sentence
        else:
            current = f"{current}\n{sentence}".strip()
    if current:
        parts.append(current.strip())
    return parts


def split_section_body(section: MarkdownSection, source: SourceDocument, max_chars: int) -> list[tuple[str, str]]:
    is_faq = source.source_type == "internal_faq" and section.heading_level >= 3
    if is_faq:
        # FAQ需要让“问题、回答、追问、边界”共同进入上下文，允许单块略长。
        return [("faq", section.body)]

    expanded: list[tuple[str, str]] = []
    for block in split_markdown_blocks(section.body):
        if TABLE_SEPARATOR_RE.search(block.splitlines()[1]) if len(block.splitlines()) > 1 else False:
            expanded.extend(("table", part) for part in split_table(block))
        elif block.lstrip().startswith("```"):
            expanded.append(("code", block))
        else:
            expanded.extend(("section", part) for part in split_long_prose(block, max_chars))

    chunks: list[tuple[str, str]] = []
    current_parts: list[str] = []
    current_types: set[str] = set()
    current_length = 0
    for block_type, block in expanded:
        if block_type == "table":
            if current_parts:
                content_type = next(iter(current_types)) if len(current_types) == 1 else "section"
                chunks.append((content_type, "\n\n".join(current_parts)))
                current_parts, current_types, current_length = [], set(), 0
            chunks.append((block_type, block))
            continue
        extra = len(block) + (2 if current_parts else 0)
        if current_parts and current_length + extra > max_chars:
            content_type = next(iter(current_types)) if len(current_types) == 1 else "section"
            chunks.append((content_type, "\n\n".join(current_parts)))
            current_parts, current_types, current_length = [], set(), 0
        current_parts.append(block)
        current_types.add(block_type)
        current_length += extra
    if current_parts:
        content_type = next(iter(current_types)) if len(current_types) == 1 else "section"
        chunks.append((content_type, "\n\n".join(current_parts)))
    return chunks


def _stable_point_id(stable_id: str) -> str:
    return str(uuid.uuid5(CHUNK_NAMESPACE, stable_id))


def chunks_for_source(
    source: SourceDocument,
    max_chars: int = DEFAULT_CHUNK_CHARS,
    image_cache_path: Path = IMAGE_CACHE_PATH,
) -> tuple[list[KnowledgeChunk], int]:
    raw = source.path.read_text(encoding="utf-8")
    normalized_original = normalize_markdown(raw)
    normalized = normalize_markdown(strip_image_references(raw)) if source.include_images else normalized_original
    image_inventory = inspect_source_images(source)
    image_cache = load_image_cache(image_cache_path)
    image_entries = image_cache.get("entries", {})
    image_revision = []
    for reference in image_inventory.references:
        entry = image_entries.get(reference.image_sha256 or "")
        image_revision.append(
            {
                "image_id": reference.image_id,
                "sha256": reference.image_sha256,
                "description": analyzed_description(entry),
                "provider": (entry or {}).get("provider"),
                "model": (entry or {}).get("model"),
            }
        )
    source_hash = (
        sha256_text(normalized_original + "\n" + json.dumps(image_revision, ensure_ascii=False, sort_keys=True))
        if source.include_images
        else sha256_text(normalized_original)
    )
    parsed_title, sections = parse_markdown_sections(normalized)
    document_title = source.title or parsed_title or source.path.stem
    chunks: list[KnowledgeChunk] = []
    empty_sections = 0

    for section in sections:
        parts = split_section_body(section, source, max_chars=max_chars)
        if not parts:
            empty_sections += 1
            continue
        section_slug = sha256_text(section.section_path)[:12]
        for ordinal, (content_type, text) in enumerate(parts, start=1):
            if len(re.sub(r"\s+", "", text)) < 15:
                empty_sections += 1
                continue
            stable_id = f"{source.document_key}|{section_slug}|{ordinal:04d}"
            embedding_text = f"{document_title}\n{section.section_path}\n{text}"
            chunks.append(
                KnowledgeChunk(
                    point_id=_stable_point_id(stable_id),
                    stable_id=stable_id,
                    document_key=source.document_key,
                    source_id=source.source_id,
                    product=source.product,
                    document_title=document_title,
                    section=section.section_path,
                    source_file=str(source.path),
                    source_type=source.source_type,
                    document_status=source.document_status,
                    known_date=source.known_date,
                    source_urls=source.source_urls,
                    content_type=content_type,
                    chunk_index=len(chunks),
                    text=text,
                    embedding_text=embedding_text,
                    source_hash=source_hash,
                    content_hash=sha256_text(text),
                )
            )

    # 图片说明只有在缓存标记为analyzed后才入库；待解析或失败不影响正文片段。
    for reference in image_inventory.references:
        entry = image_entries.get(reference.image_sha256 or "")
        description = analyzed_description(entry)
        if not reference.exists or not description:
            continue
        stable_id = f"{source.document_key}|image|{reference.image_id}"
        context = "\n".join(
            value
            for value in (reference.adjacent_before, reference.adjacent_after)
            if value.strip()
        )
        embedding_text = "\n".join(
            value
            for value in (document_title, reference.section, context, description)
            if value.strip()
        )
        chunks.append(
            KnowledgeChunk(
                point_id=_stable_point_id(stable_id),
                stable_id=stable_id,
                document_key=source.document_key,
                source_id=source.source_id,
                product=source.product,
                document_title=document_title,
                section=reference.section,
                source_file=str(source.path),
                source_type=source.source_type,
                document_status=source.document_status,
                known_date=source.known_date,
                source_urls=source.source_urls,
                content_type="image_description",
                chunk_index=len(chunks),
                text=description,
                embedding_text=embedding_text,
                source_hash=source_hash,
                content_hash=sha256_text(description),
                asset_type="image",
                image_id=reference.image_id,
                image_path=reference.image_path,
                image_sha256=reference.image_sha256,
                image_alt_text=reference.alt_text,
                image_adjacent_before=reference.adjacent_before,
                image_adjacent_after=reference.adjacent_after,
                image_description_generated=True,
                image_description_provider=(entry or {}).get("provider"),
                image_description_model=(entry or {}).get("model"),
            )
        )
    return chunks, empty_sections


def build_corpus(
    sources: Iterable[SourceDocument] = SOURCES,
    max_chars: int = DEFAULT_CHUNK_CHARS,
) -> tuple[list[KnowledgeChunk], BuildReport]:
    source_list = list(sources)
    report = BuildReport(configured_files=len(source_list))
    candidates: list[KnowledgeChunk] = []
    for source in source_list:
        if not source.path.is_file():
            report.missing_files += 1
            report.missing_paths.append(str(source.path))
            report.skipped.append({"source_id": source.source_id, "reason": "文件不存在"})
            continue
        report.found_files += 1
        source_chunks, empty_count = chunks_for_source(source, max_chars=max_chars)
        report.empty_sections += empty_count
        report.generated_chunks += len(source_chunks)
        candidates.extend(source_chunks)

    # 对飞书副本或重复段落做内容级去重，优先保留清单中靠前的来源。
    seen: dict[str, str] = {}
    kept: list[KnowledgeChunk] = []
    for chunk in candidates:
        key = normalized_content_key(chunk.text)
        if key in seen:
            report.duplicate_chunks += 1
            report.skipped.append(
                {
                    "source_id": chunk.source_id,
                    "reason": "片段正文重复",
                    "duplicate_of": seen[key],
                }
            )
            continue
        seen[key] = chunk.stable_id
        kept.append(chunk)
    report.kept_chunks = len(kept)
    return kept, report


def original_section_text(source: SourceDocument, section_path: str) -> str | None:
    if not source.path.is_file():
        return None
    _, sections = parse_markdown_sections(source.path.read_text(encoding="utf-8"))
    for section in sections:
        if section.section_path == section_path:
            return section.body
    return None


def write_chunk_preview(chunks: Sequence[KnowledgeChunk], report: BuildReport, output: Path, limit: int = 18) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Qdrant知识库片段预览",
        "",
        "> 由本地预处理生成，不包含Embedding，也未写入Qdrant。",
        "",
        "## 统计",
        "",
        "```json",
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        "```",
        "",
        "## 片段样例",
    ]
    for chunk in chunks[:limit]:
        lines.extend(
            [
                "",
                f"### {chunk.document_title}｜{chunk.section}",
                "",
                f"- Point ID：`{chunk.point_id}`",
                f"- 类型：`{chunk.content_type}` / `{chunk.source_type}`",
                f"- 状态：`{chunk.document_status}`",
                f"- 来源：`{chunk.source_file}`",
                "",
                chunk.text,
            ]
        )
    output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
