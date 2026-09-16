from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from .images import ImageReference


VISION_SYSTEM_PROMPT = """你负责为本地知识库生成图片说明。只描述图片中实际可见的信息。
不要根据相邻正文补造图片内容；看不清的文字、数字、品牌或关系必须写入uncertainties。
返回一个JSON对象，字段必须为visible_text、summary、structure、relationships、uncertainties，值均为中文字符串。
visible_text只记录有把握的可见文字；summary概括画面；structure描述布局；relationships描述箭头、层级或对照关系。"""


def _data_url(path: Path) -> str:
    suffix = path.suffix.lower()
    media_type = "image/png" if suffix == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _parse_json_object(text: str) -> dict[str, str]:
    cleaned = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.S | re.I)
    if fenced:
        cleaned = fenced.group(1)
    data = json.loads(cleaned)
    required = ("visible_text", "summary", "structure", "relationships", "uncertainties")
    if not isinstance(data, dict) or any(key not in data for key in required):
        raise ValueError("视觉模型没有返回约定的JSON字段")
    return {key: str(data.get(key, "")).strip() for key in required}


def analyze_with_bailian_openai_compatible(
    reference: ImageReference,
    api_key: str,
    model: str,
    base_url: str,
) -> dict[str, str]:
    """发送单张原图及最小章节上下文；调用方必须先取得用户的外发授权。"""
    if not api_key.strip():
        raise ValueError("缺少DASHSCOPE_API_KEY")
    if not model.strip():
        raise ValueError("缺少BAILIAN_VISION_MODEL，请填写百炼控制台中实际可用的视觉模型ID")
    if not reference.exists:
        raise FileNotFoundError(reference.image_path)
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("未安装可选依赖openai；不要为本地检索单独安装，确认调用视觉模型后再安装") from exc

    context = (
        f"文档：{reference.document_title}\n"
        f"章节：{reference.section}\n"
        f"图片前相邻正文：{reference.adjacent_before or '无'}\n"
        f"图片后相邻正文：{reference.adjacent_after or '无'}\n"
        "相邻正文只用于定位主题，不得作为图片中可见内容。"
    )
    with OpenAI(api_key=api_key.strip(), base_url=base_url.rstrip("/")) as client:
        response = client.chat.completions.create(
            model=model.strip(),
            messages=[
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": context},
                        {
                            "type": "image_url",
                            "image_url": {"url": _data_url(Path(reference.image_path))},
                        },
                    ],
                },
            ],
            stream=False,
        )
    content = response.choices[0].message.content or ""
    return _parse_json_object(content)

