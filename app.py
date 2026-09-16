from __future__ import annotations

import os
import re
import time
from pathlib import Path

import streamlit as st

from knowledge_assistant.config import (
    COLLECTION_NAME,
    DEFAULT_CACHE_DIR,
    IMAGE_CACHE_PATH,
    QDRANT_URL,
)
from knowledge_assistant.embedding import LocalEmbedder
from knowledge_assistant.generation import generate_with_truefoundry
from knowledge_assistant.images import inspect_all_images, load_image_cache, strip_image_references
from knowledge_assistant.manifest import SOURCES, source_by_id
from knowledge_assistant.preprocess import original_section_text
from knowledge_assistant.store import collection_count, document_chunks, make_client, search


SOURCE_TYPE_LABELS = {
    "internal_presales": "内部售前手册",
    "internal_faq": "内部FAQ",
    "technical_note": "技术学习笔记",
    "experiment_guide": "实验说明",
    "cloud_doc_export": "飞书云文档导出",
    "technical_explainer": "技术原理说明",
    "experiment_record": "历史实验记录",
    "simulated_solution": "模拟场景方案",
    "marketing_case_analysis": "案例解读文章",
    "trip_report": "出差记录/会议观点与厂商介绍",
}

AUTO_ROUTING_MODEL = "qdrant-truefoundry-demo/qdrant-truefoundry-demo"
DIRECT_MODEL = "self-hosted-model/deepseek-syj"


st.set_page_config(page_title="AI产品知识问答", page_icon="🔎", layout="wide")


@st.cache_resource(show_spinner="加载本地中文Embedding模型……")
def get_embedder() -> LocalEmbedder:
    return LocalEmbedder(cache_dir=DEFAULT_CACHE_DIR, allow_download=False)


@st.cache_resource(show_spinner=False)
def get_client(url: str, api_key: str | None):
    return make_client(url=url, api_key=api_key)


@st.cache_data(show_spinner=False)
def allowed_image_paths() -> set[str]:
    """只允许展示显式资料清单中解析成功的图片，不接受页面传入任意本地路径。"""
    inventory = inspect_all_images(SOURCES)
    return {
        str(Path(reference.image_path).resolve())
        for reference in inventory.references
        if reference.exists
    }


def render_linked_image(payload: dict) -> None:
    if payload.get("asset_type") != "image":
        return
    image_path = payload.get("image_path")
    if not image_path:
        return
    resolved = str(Path(image_path).resolve())
    if resolved not in allowed_image_paths() or not Path(resolved).is_file():
        st.warning("关联原图不在当前资料清单或已不存在，未展示。")
        return
    st.image(resolved, caption=f"关联原图｜图片ID：{payload.get('image_id', '')}")
    st.caption("上方说明由视觉模型预先生成并缓存；当前回答模型依据说明文字作答，并未实时查看原图。")


def connect_sidebar():
    st.sidebar.header("本地检索配置")
    url = st.sidebar.text_input("Qdrant地址", value=QDRANT_URL)
    collection = st.sidebar.text_input("独立Collection", value=COLLECTION_NAME)
    api_key = st.sidebar.text_input(
        "Qdrant API Key（本地无鉴权可留空）",
        value=os.getenv("QDRANT_KB_API_KEY", ""),
        type="password",
    )
    return get_client(url, api_key or None), collection


def render_sources(results) -> None:
    st.subheader("本次实际检索来源")
    for index, result in enumerate(results, start=1):
        payload = result.payload
        label = f"[{index}] {payload.get('document_title', '')}｜{payload.get('section', '')}｜分数 {result.score:.4f}"
        with st.expander(label):
            st.caption(
                f"资料类型：{SOURCE_TYPE_LABELS.get(payload.get('source_type'), payload.get('source_type'))}　"
                f"状态：{payload.get('document_status', '')}"
            )
            st.markdown(result.text)
            render_linked_image(payload)
            st.code(payload.get("source_file", ""), language=None)
            if payload.get("source_urls"):
                st.write("文档记录的参考链接：", payload["source_urls"])


def page_qa(client, collection: str) -> None:
    st.title("AI产品知识问答")
    st.caption("回答与来源分开显示；检索分数表示向量相似程度，不是答案正确率。")
    question = st.text_area("请输入问题", placeholder="例如：Payload过滤能不能直接作为权限系统？")
    top_k = st.slider("召回片段数量", min_value=2, max_value=10, value=5)

    with st.expander("可选：TrueFoundry回答模型", expanded=True):
        enable_generation = st.checkbox("① 启用回答模型生成带引用回答", value=False)
        model_entry = st.selectbox(
            "模型入口",
            ("Auto Routing Virtual Model", "原模型入口"),
            help="Auto Routing为本次演示入口；原入口保留用于切回和问题定位。",
        )
        default_model = AUTO_ROUTING_MODEL if model_entry.startswith("Auto") else DIRECT_MODEL
        model = st.text_input(
            "模型ID",
            value=default_model,
            key=f"tfy_model_{model_entry}",
        )
        base_url = st.text_input("Gateway地址", value="https://gateway.truefoundry.ai")
        token = st.text_input("② TrueFoundry Gateway Token", type="password")
        allow_external = st.checkbox(
            "③ 我确认允许将本次问题和实际召回片段发送到上述Gateway",
            value=False,
        )
        st.caption(
            "这里需要TrueFoundry Gateway Token；DASHSCOPE_API_KEY只用于百炼图片解析，不能替代。"
            "本次调用沿用已跑通示例并开启TrueFoundry请求日志，用于观察路由；"
            "发送范围仍只有当前问题和本次召回片段。"
        )
        if model == AUTO_ROUTING_MODEL:
            st.info(
                "Auto Routing判断的是实际发送的单轮请求，其中包括系统提示、用户问题和召回上下文。"
                "页面不发送历史会话；实际服务档位还可能受升级或回退影响。"
            )
        if enable_generation and token.strip() and allow_external:
            st.success("回答模型配置已就绪。")
        elif allow_external and not enable_generation:
            st.warning("已经授权外发，但还没有勾选第①项“启用回答模型”。")
        elif enable_generation and not token.strip():
            st.warning("已经启用回答模型，但第②项TrueFoundry Gateway Token为空。")
        elif enable_generation and not allow_external:
            st.warning("已经启用回答模型并填写Token，但还没有勾选第③项外发授权。")

    if not st.button("检索并回答", type="primary"):
        return
    if not question.strip():
        st.warning("请先输入问题。")
        return
    try:
        embedder = get_embedder()
        started = time.perf_counter()
        query_vector = embedder.embed_texts([question.strip()])[0]
        results = search(client, query_vector, top_k=top_k, collection_name=collection)
        retrieval_elapsed = time.perf_counter() - started
    except Exception as exc:
        st.error(f"本地检索未完成：{exc}")
        return

    metric_left, metric_right = st.columns(2)
    metric_left.metric("检索耗时（含问题向量化）", f"{retrieval_elapsed:.3f} 秒")
    if not results:
        metric_right.metric("生成耗时", "未执行")
        st.warning("当前没有检索到片段。这不能单独证明产品不支持该问题。")
        return

    if enable_generation and token.strip() and allow_external:
        try:
            st.subheader("依据资料生成的回答")
            streamed_answer = st.empty()

            def show_stream(partial_text: str) -> None:
                streamed_answer.markdown(partial_text + "▌")

            answer = generate_with_truefoundry(
                question.strip(),
                results,
                token=token,
                model=model,
                base_url=base_url,
                on_text=show_stream,
            )
            metric_right.metric("生成耗时", f"{answer.elapsed_seconds:.3f} 秒")
            streamed_answer.markdown(answer.text)
            if any(item.payload.get("asset_type") == "image" for item in results):
                st.info("本次上下文包含预先生成的图片说明；回答模型没有直接查看原图。")
            if answer.invalid_citations_removed:
                st.warning(f"已移除模型返回的无效引用编号：{answer.invalid_citations_removed}")

            st.subheader("本次模型调用")
            st.table(
                [
                    {
                        "请求模型": answer.requested_model,
                        "实际服务模型": answer.resolved_model or "未返回",
                        "实际服务档位": answer.route_tier or "未返回",
                        "判断原因": answer.route_cause or "未返回",
                    }
                ]
            )
            if answer.total_tokens is None:
                token_summary = "未返回"
            else:
                token_summary = (
                    f"输入 {answer.prompt_tokens if answer.prompt_tokens is not None else '未返回'} / "
                    f"输出 {answer.completion_tokens if answer.completion_tokens is not None else '未返回'} / "
                    f"合计 {answer.total_tokens}"
                )
            citation_status = (
                "包含有效引用编号"
                if re.search(r"\[\d+\]", answer.text)
                else "未返回有效引用编号"
            )
            st.caption(
                f"检索上下文长度：{answer.context_chars} 字符｜"
                f"应用侧生成耗时：{answer.elapsed_seconds:.3f} 秒｜"
                f"Token用量：{token_summary}｜引用状态：{citation_status}"
            )
            st.caption(
                "“实际服务档位”来自x-tfy-applied-rules，不等同于原始问题难度；"
                "“实际服务模型”来自x-tfy-resolved-model。缺失字段按未返回展示。"
            )
        except Exception as exc:
            metric_right.metric("生成耗时", "失败")
            st.error(f"回答生成失败，但下方本地检索结果仍可查看：{exc}")
    else:
        metric_right.metric("生成耗时", "未执行")
        missing: list[str] = []
        if not enable_generation:
            missing.append("未勾选①启用回答模型")
        if not token.strip():
            missing.append("②TrueFoundry Gateway Token为空")
        if not allow_external:
            missing.append("未勾选③外发授权")
        st.warning("回答未生成：" + "；".join(missing) + "。本地检索结果仍可在下方核对。")
    render_sources(results)


def render_result_cards(results, title: str) -> None:
    st.markdown(f"**{title}**")
    if not results:
        st.caption("没有结果")
        return
    for index, result in enumerate(results, start=1):
        marker = "🖼️ " if result.payload.get("asset_type") == "image" else ""
        st.markdown(
            f"{index}. {marker}`{result.score:.4f}`　{result.payload.get('document_title', '')}　"
            f"{result.payload.get('section', '')}"
        )
        st.caption(result.text[:260] + ("……" if len(result.text) > 260 else ""))
        render_linked_image(result.payload)


def page_retrieval_explainer(client, collection: str) -> None:
    st.title("检索原理展示")
    st.caption("页面与知识问答复用同一Embedding模型和search函数。")
    try:
        total = collection_count(client, collection)
    except Exception as exc:
        st.error(f"暂时无法读取Collection：{exc}")
        st.info("请先启动本地Qdrant并执行 `python ingest.py`。")
        return
    st.success(f"当前Collection共有 {total} 个知识片段。")

    st.header("1. 文档如何入库")
    source = st.selectbox(
        "选择文档",
        SOURCES,
        format_func=lambda item: f"{item.title}（{SOURCE_TYPE_LABELS.get(item.source_type, item.source_type)}）",
    )
    stored = document_chunks(client, source.document_key, collection_name=collection, with_vectors=True)
    if not stored:
        st.warning("该清单文件尚未在当前Collection中找到片段。")
    else:
        selected = st.selectbox(
            "选择切分片段",
            stored,
            format_func=lambda item: f"#{item.payload.get('chunk_index', 0) + 1} {item.payload.get('section', '')}",
        )
        original = original_section_text(source_by_id(source.source_id), selected.payload.get("section", ""))
        left, right = st.columns(2)
        with left:
            st.markdown("**原文对应章节**")
            st.caption(f"{source.path}｜{selected.payload.get('section', '')}")
            st.markdown(strip_image_references(original) if original else "当前未能按章节路径恢复原文。")
        with right:
            st.markdown("**切分后写入Qdrant的片段**")
            st.markdown(selected.text)
            render_linked_image(selected.payload)
            st.code(f"Point ID: {selected.point_id}", language=None)
            vector = selected.vector or []
            st.write(f"向量维度：{len(vector)}")
            st.code(str([round(value, 6) for value in vector[:8]]), language=None)
            st.caption("这里只展示前8个数值；单个维度不对应人工指定的业务含义。")
            payload_preview = {key: value for key, value in selected.payload.items() if key != "text"}
            st.json(payload_preview)

    st.header("2. 问题如何查询")
    query = st.text_input("演示问题", value="Payload过滤能否直接作为权限系统？")
    top_k = st.slider("Top-K", min_value=2, max_value=8, value=4, key="explain_top_k")
    if st.button("执行向量检索", key="run_query"):
        try:
            embedder = get_embedder()
            query_vector = embedder.embed_texts([query])[0]
            results = search(client, query_vector, top_k=top_k, collection_name=collection)
            st.write(f"问题向量维度：{len(query_vector)}")
            st.code(str([round(value, 6) for value in query_vector[:8]]), language=None)
            st.caption("Cosine相似度按当前Collection配置计算；分数不是答案正确率。")
            render_result_cards(results, "实际Top-K结果")
        except Exception as exc:
            st.error(f"查询失败：{exc}")

    st.header("3. 过滤如何影响结果")
    filter_query = st.text_input("同一问题", value="Qdrant适合怎样的客户场景？", key="filter_query")
    available_types = sorted({source.source_type for source in SOURCES})
    selected_type = st.selectbox(
        "仅允许参与检索的资料类型",
        available_types,
        index=available_types.index("simulated_solution"),
        format_func=lambda value: SOURCE_TYPE_LABELS.get(value, value),
    )
    if st.button("对比过滤前后", key="run_filter"):
        try:
            embedder = get_embedder()
            vector = embedder.embed_texts([filter_query])[0]
            before = search(client, vector, top_k=4, collection_name=collection)
            after = search(
                client,
                vector,
                top_k=4,
                collection_name=collection,
                source_type=selected_type,
            )
            left, right = st.columns(2)
            with left:
                render_result_cards(before, "过滤前：所有资料")
            with right:
                render_result_cards(after, f"过滤后：{SOURCE_TYPE_LABELS.get(selected_type, selected_type)}")
            st.info("向量检索寻找语义相关内容；过滤条件限定允许参与检索的资料范围。")
        except Exception as exc:
            st.error(f"过滤对比失败：{exc}")


def page_image_inventory() -> None:
    st.title("图文资料检查")
    st.caption("这里展示显式资料清单中的本地图片、章节关联和解析状态；打开页面不会调用外部模型。")
    inventory = inspect_all_images(SOURCES)
    cache = load_image_cache(IMAGE_CACHE_PATH)
    entries = cache.get("entries", {})
    left, middle, right = st.columns(3)
    left.metric("图片引用", len(inventory.references))
    middle.metric("缺失或越界", len(inventory.missing))
    right.metric("未被引用", len(inventory.unreferenced))
    references = list(inventory.references)
    if not references:
        st.info("当前资料清单中没有启用图片关联的文档。")
        return
    selected = st.selectbox(
        "选择图片",
        references,
        format_func=lambda item: f"第{item.line_number}行｜{item.section}｜{item.relative_path}",
    )
    entry = entries.get(selected.image_sha256 or "", {})
    st.markdown(f"**所属章节：** {selected.section}")
    render_linked_image(
        {
            "asset_type": "image",
            "image_path": selected.image_path,
            "image_id": selected.image_id,
        }
    )
    context_left, context_right = st.columns(2)
    with context_left:
        st.markdown("**图片前相邻正文**")
        st.caption(selected.adjacent_before or "无")
    with context_right:
        st.markdown("**图片后相邻正文**")
        st.caption(selected.adjacent_after or "无")
    status = entry.get("status", "pending")
    if status == "analyzed":
        st.success(
            f"图片说明已缓存｜服务：{entry.get('provider', '')}｜模型：{entry.get('model', '')}"
        )
        for label, key in (
            ("可见文字", "visible_text"),
            ("内容概述", "summary"),
            ("主要结构", "structure"),
            ("关键关系", "relationships"),
            ("不确定内容", "uncertainties"),
        ):
            if entry.get(key):
                st.markdown(f"**{label}：** {entry[key]}")
        st.caption("以上为模型生成的图片说明，不是Markdown原文。")
    elif status == "failed":
        st.warning(f"图片解析失败，正文仍可入库。缓存错误：{entry.get('error', '')}")
    else:
        st.info("待解析：目前只有本地路径、章节和相邻正文，没有生成图片内容说明。")


def main() -> None:
    client, collection = connect_sidebar()
    page = st.sidebar.radio("页面", ("知识问答", "检索原理展示", "图文资料检查"))
    if page == "知识问答":
        page_qa(client, collection)
    elif page == "检索原理展示":
        page_retrieval_explainer(client, collection)
    else:
        page_image_inventory()


if __name__ == "__main__":
    main()
