from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
from fastembed import TextEmbedding

from .config import DEFAULT_CACHE_DIR, EMBEDDING_MODEL, EXPECTED_VECTOR_SIZE


class LocalEmbedder:
    """只使用本地FastEmbed缓存；默认不允许在运行时静默下载模型。"""

    def __init__(
        self,
        model_name: str = EMBEDDING_MODEL,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        allow_download: bool = False,
    ) -> None:
        self.model_name = model_name
        self.cache_dir = Path(cache_dir)
        if not self.cache_dir.is_dir() and not allow_download:
            raise FileNotFoundError(
                f"未找到FastEmbed缓存目录：{self.cache_dir}。"
                "请先确认模型缓存，或明确使用 --allow-model-download。"
            )
        self._model = TextEmbedding(
            model_name=model_name,
            cache_dir=str(self.cache_dir),
            local_files_only=not allow_download,
        )
        probe = self.embed_texts(["Qdrant向量检索维度检查"])[0]
        self.dimension = len(probe)
        if self.dimension != EXPECTED_VECTOR_SIZE:
            raise ValueError(
                f"Embedding实际维度为{self.dimension}，预期为{EXPECTED_VECTOR_SIZE}；"
                "停止创建或写入Collection，避免配置不一致。"
            )

    def embed_texts(self, texts: Iterable[str]) -> list[list[float]]:
        values: list[list[float]] = []
        for vector in self._model.embed(list(texts)):
            array = np.asarray(vector, dtype=np.float32)
            if not np.isfinite(array).all():
                raise ValueError("Embedding包含NaN或Infinity")
            values.append(array.tolist())
        return values
