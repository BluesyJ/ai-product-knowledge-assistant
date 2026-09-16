# AI产品线知识问答助手 V0.2（文本基线＋图文资料接入）

这是一个本地RAG原型：保留原有15份Qdrant资料，并显式新增1份图文出差报告。Streamlit提供知识问答、检索原理展示和图文资料检查。程序不递归抓取所有文档、不修改原资料，也不把出差记录、会议观点或厂商介绍标成Qdrant官方材料。

## 当前范围和状态

| 项目 | 状态 |
|---|---|
| 16份显式资料清单 | 原15份Qdrant资料＋1份外滩大会出差报告，路径均存在 |
| Markdown与图片说明预处理 | 离线检查通过：16份文件生成330个正文片段和13个图片说明片段，共343个 |
| 图文关联 | 13个引用均能解析到本地图片；无缺图、未引用图或重复内容 |
| 图片说明 | 已获授权并由百炼`qwen3.7-flash`完成13张解析，失败0张；结果按图片哈希缓存 |
| 本地Embedding | 已发现FastEmbed缓存；`BAAI/bge-small-zh-v1.5`离线实测512维 |
| Qdrant重复入库和文档更新 | Qdrant内存模式检查通过；相同文件跳过，变更后按文档替换，来源类型过滤生效 |
| Streamlit界面 | 原文本版已由用户启动查看；“图文资料检查”可读取缓存，图片命中展示待入库后验收 |
| 本地Qdrant服务器检索 | 当前`127.0.0.1:6333`连接被拒绝；343个片段尚未完成持久化入库 |
| TrueFoundry回答生成 | 已接入Auto Routing流式入口及路由响应头展示；代码和离线解析检查完成，真实RAG调用由用户运行验证 |
| 必要离线测试 | 14项通过；原版另用真实512维Embedding完成30个样例片段的内存检索冒烟测试 |

“代码完成”“离线检查通过”“本地Qdrant服务器运行通过”“外部模型生成通过”分别记录，不能互相替代。

## 目录

```text
app.py                              Streamlit问答、检索原理和图文资料检查
ingest.py                           预览和入库命令
knowledge_assistant/manifest.py     16份资料清单及来源状态
knowledge_assistant/preprocess.py   标题、FAQ、表格和代码块切分
knowledge_assistant/images.py       图片引用、章节关联、哈希缓存与白名单
knowledge_assistant/vision.py       百炼OpenAI兼容视觉接口（默认不调用）
knowledge_assistant/embedding.py    本地FastEmbed封装
knowledge_assistant/store.py        Collection、更新、检索和过滤
knowledge_assistant/generation.py   TrueFoundry流式回答、Auto Routing响应头及引用校验
evaluation_questions.json           15条固定评价问题，不参与入库
auto_routing_test_questions.json    6条真实RAG路由测试问题，不参与入库
artifacts/chunk_preview.md           离线生成的切片预览
docs/DEMO_SCRIPT.md                  5～8分钟演示顺序
docs/IMAGE_INGEST.md                 图文接入、数据边界和验证说明
docs/AUTO_ROUTING_TEST.md            Auto Routing配置边界、六题步骤和记录表
analyze_images.py                    本地图片清单；授权后才可调用视觉模型
```

## 环境准备

```powershell
conda activate qdrant-poc
cd D:\SYJProject\HongKe\Demos\ai_product_knowledge_assistant
python -c "import sys; print(sys.executable)"
```

安装本地检索页面依赖：

```powershell
python -m pip install -r requirements.txt
```

只有需要TrueFoundry生成回答时再安装：

```powershell
python -m pip install -r requirements-generation.txt
```

真实Token不写入`.env`、源码、截图或日志。页面使用密码输入框，仅保存在当前Streamlit会话内存中。

## 1. 只检查切分，不连接Qdrant

```powershell
python ingest.py --preview-only
```

命令会检查16份路径、输出文本片段统计，并更新图片清单、说明缓存和`artifacts/chunk_preview.md`。没有成功缓存的图片说明不会入库，但正文仍可正常处理。

只建立本地图片清单和待解析缓存：

```powershell
python analyze_images.py
```

该命令不读取图片内容、不调用模型，也不发送数据。视觉模型配置、外发内容和授权步骤见[docs/IMAGE_INGEST.md](docs/IMAGE_INGEST.md)。

## 2. 入库与更新

先确认本地Qdrant已在`http://localhost:6333`运行，然后执行：

```powershell
python ingest.py
```

默认Collection为`ai_product_kb_qdrant_v01`，与原Qdrant实验Collection分开。程序不会删除其他Collection：

- 首次运行：创建Collection并写入全部片段；
- 文件未变化：Point ID、数量和源文件哈希一致时跳过；
- 文件已修改：只删除该文档的旧片段，再写入新片段；
- 文件暂时缺失：报告为跳过，不自动删除已有知识。

如使用不同地址，在当前终端设置：

```powershell
$env:QDRANT_KB_URL="http://localhost:6333"
$env:QDRANT_KB_COLLECTION="ai_product_kb_qdrant_v01"
```

## 3. 启动页面

```powershell
streamlit run app.py
```

### 页面一：知识问答

- 输入问题并选择Top-K；
- 始终先完成本地Embedding和Qdrant检索；
- 没有回答模型时仍展示真实来源；
- 默认回答入口为Virtual Model `qdrant-truefoundry-demo/qdrant-truefoundry-demo`，下拉框保留原模型入口用于切回；
- 生成回答需要同时完成三项：勾选启用、输入TrueFoundry Gateway Token、勾选本次资料外发确认；百炼`DASHSCOPE_API_KEY`不能替代Gateway Token；
- 调用沿用已跑通的`stream=True`形式，完整消费并关闭响应流；页面逐步显示回答；
- 页面分别显示检索耗时与生成耗时，并从实际响应头展示请求模型、实际服务模型、实际服务档位和判断原因；缺失字段显示“未返回”；
- Token用量只在流式接口实际返回usage时展示，不由应用推算；
- 命中图片说明时展示白名单内的本地原图，并明确回答模型只看到了预生成说明。

Auto Routing展示使用：

- `x-tfy-resolved-model`：实际服务模型；
- `x-tfy-applied-rules`中的`complexity.tier`：实际服务档位；
- `x-tfy-applied-rules`中的`complexity.cause`：判断原因。

实际服务档位不等同于原始问题难度。网关处理的是系统提示、用户问题和本次召回上下文组成的真实请求，且最终档位还可能受会话固定、升级或回退影响。本页面不发送多轮历史。六条人工验证问题及记录方法见[docs/AUTO_ROUTING_TEST.md](docs/AUTO_ROUTING_TEST.md)。

### 页面二：检索原理展示

- 选择文档和片段，查看原文章节、Point ID、向量维度、向量前8项和Payload；
- 输入问题查看实际Top-K、Cosine相似度和来源；
- 用`source_type`对同一问题比较过滤前后结果；
- 不把相似度分数称为答案正确率，不解释单个向量维度的业务含义。

### 页面三：图文资料检查

- 不连接视觉模型即可查看13张白名单本地图片；
- 显示图片所属章节、前后相邻正文和缓存状态；
- 解析完成后显示模型、可见文字、结构、关键关系和不确定内容。

## 回答模型与数据流向

本地检索不会向外部发送资料。启用TrueFoundry生成时，只发送当前问题和本次Top-K片段，不发送整个知识库。若Top-K包含图片说明，发送的是说明文字，不是原图。Auto Routing调用沿用用户提供的成功示例，显式开启TrueFoundry请求日志以观察路由；具体日志内容和留存仍取决于Gateway侧配置。

图片预解析是另一条独立数据流：只有显式执行`analyze_images.py --execute --confirm-external-upload`时，才会把单张原图、文档标题、所属章节及前后相邻正文发送到配置的百炼视觉接口。第一版不要求经过TrueFoundry。

当前阶段只使用图片Caption的文本向量，不生成原图Embedding，也不提供以图搜图。后续只有在确认合适的多模态Embedding模型后才单独扩展，不与本轮Caption流程混在一起。

如果资料不能外发，不要勾选页面授权；本地检索与来源展示不受影响。若需要完全本地生成，应另行确认本地大模型和资源，不在V0.1中自动下载或部署。

## 关键函数调用链

```text
manifest.SOURCES
→ images.inspect_all_images / 本地SHA-256缓存
→ preprocess.build_corpus
→ embedding.LocalEmbedder.embed_texts
→ store.ensure_collection / store.ingest_chunks

用户问题
→ LocalEmbedder.embed_texts
→ store.search
→ 页面展示真实来源
→（可选且用户确认外发）generation.generate_with_truefoundry
```

## 固定评价问题

`evaluation_questions.json`保存原Qdrant范围的15条问题；`image_evaluation_questions.json`保存5条图文增强问题。评价文件都不在16份入库清单中，不会成为模型答案的资料来源。

离线检查：

```powershell
python -m unittest discover -s tests -v
```

完整演示顺序见[docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)。
