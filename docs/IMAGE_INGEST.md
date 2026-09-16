# 出差报告图文接入说明

## 1. 当前资料检查结果

- 资料目录：`D:\虹科\云文档\出差报告`
- Markdown：`2026外滩大会.md`，1份。
- 图片：`图片和附件`下13张JPG，均为1707×1280。
- 引用格式：标准Markdown相对路径，例如`![文件名](图片和附件/文件名.jpg)`。
- 13个引用均能解析到本地文件；无缺图、无未引用图片、无相同内容哈希的重复图片。
- 图片集中在4个三级章节，能够关联到章节和前后相邻正文。

资料在清单中标记为：

- `product=ai_security`
- `source_type=trip_report`
- `document_status=personal_trip_report_meeting_notes_and_vendor_presentations`

它表示个人出差记录、会议观点和现场厂商介绍，不是Qdrant官方资料，也不是经过独立核实的产品能力证明。

## 2. 第一版处理链路

```text
显式资料清单
→ 解析Markdown图片引用
→ 校验图片仍位于该文档目录内
→ 记录章节、相邻正文、图片ID、路径和SHA-256
→ 以SHA-256建立图片说明缓存
→ 成功说明单独生成image_description片段
→ 使用现有文本Embedding写入同一独立Collection
→ 命中时展示说明及白名单中的本地原图
```

图片标记从普通正文切分中移除，避免把随机文件名当成知识。图片说明只有在缓存状态为`analyzed`时才入库；`pending`或`failed`不影响正文入库。

Qdrant保存说明文字、向量和来源元数据，不保存原图文件。说明片段包含：图片ID、原图路径、图片哈希、文档、章节、相邻正文、解析服务和模型。说明正文固定标记为“模型生成的图片说明，非原文”。

## 3. 本地产物

- `artifacts/image_inventory.json`：图片引用和关联清单。
- `artifacts/image_descriptions.json`：按图片内容SHA-256缓存解析结果。
- `analyze_images.py`：默认只刷新上述本地清单；不会调用外部服务。

相同图片内容重复出现，或重复执行入库时，成功缓存不会再次调用视觉模型。图片内容发生变化后哈希改变，会形成新的待解析项。

## 4. 百炼最简接入方案

第一版直接使用阿里百炼的OpenAI兼容视觉接口，不把TrueFoundry作为必要前提。代码不保存或打印密钥。

需要用户在本机确认并配置：

- `DASHSCOPE_API_KEY`：百炼API Key，仅放入当前运行环境。
- `BAILIAN_VISION_MODEL`：百炼控制台中实际可用、支持图片输入的准确模型ID，不由程序猜测。
- `BAILIAN_VISION_BASE_URL`：可选；默认`https://dashscope.aliyuncs.com/compatible-mode/v1`，需结合账号地域和控制台说明确认。
- 可选依赖`openai`：当前`qdrant-poc`环境已可导入；若后续换环境且缺失，获得安装确认后再安装`requirements-generation.txt`。

一次调用会外发：

1. 一张原始JPG的完整字节；
2. 文档标题；
3. 所属章节；
4. 图片前后最多各3行相邻正文；
5. 固定的图片解析指令。

不会外发整个知识库、其他图片、Qdrant数据或API Key。是否记录请求正文仍取决于百炼侧账号和日志配置。

获得用户确认后才执行：

```powershell
python analyze_images.py --execute --confirm-external-upload
python ingest.py
```

`--execute`单独出现仍会被程序阻止。解析失败会在缓存中记录失败状态，正文仍可入库。成功后再次运行`python ingest.py`，图片说明才会生成向量并写入Qdrant。

## 5. 页面和安全边界

- 图片说明参与现有语义检索，不新增另一套检索算法。
- 页面只允许展示显式资料清单中解析成功的本地图片路径，不接受用户输入任意文件路径。
- TrueFoundry回答模型只接收召回的说明文字，不接收原图；页面和提示词均明确它没有实时查看图片。
- 本阶段不提供“检索后再把原图发送给视觉模型回答”的实时视觉问答。

## 6. 验证问题

问题清单保存在`image_evaluation_questions.json`，覆盖正文、图片及图文结合三类。13张图片已由百炼`qwen3.7-flash`生成结构化说明，失败0张；当前共形成330个正文片段和13个图片说明片段。由于本地Qdrant服务尚未启动，图片问题的实际召回、原图展示和回答引用仍待入库后验证，不能把Caption生成等同于图文检索验收通过。

当前范围仅为“图片→Caption→文本Embedding→Qdrant”。原图Embedding、双命名向量及以图搜图暂不实施，待后续确认百炼是否提供适合的多模态Embedding模型后再单独评估。
