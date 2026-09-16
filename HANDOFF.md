# AI产品线知识问答助手阶段交接

> 交接日期：2026年9月16日  
> 项目目录：`D:\SYJProject\HongKe\Demos\ai_product_knowledge_assistant`  
> 当前版本定位：本地RAG演示原型，文本基线已扩展为“文本＋预生成图片说明”，不是正式部门知识库。

## 1. 本阶段实际完成

- 建立16份显式资料清单：原15份Qdrant资料，加1份`2026外滩大会.md`图文出差报告。新文件不会因放入目录而自动入库。
- 实现Markdown分章节切分，保留标题层级、完整FAQ、表格表头和代码块边界；Payload记录文档、章节、来源类型、状态、日期、链接等信息。
- 实现稳定Point ID、按文档哈希跳过未变资料、文档变化后替换该文档旧片段，以及`source_type`过滤。
- 保留知识问答页和检索原理展示页，新增图文资料检查页；图片说明命中时可展示白名单内的本地原图。
- 检查出差报告的13张JPG：引用全部有效，无缺图、未引用图或重复内容；建立章节、相邻正文、图片ID、路径和SHA-256关联。
- 经用户明确授权，使用百炼`qwen3.7-flash`为13张图片生成结构化Caption并缓存，失败0张。Caption包含可见文字、内容概述、结构、关键关系和不确定内容。
- 实现可选TrueFoundry回答入口及真实召回来源编号校验；未配置生成模型时仍可完成本地检索和来源展示。
- 最近一次界面修改将回答模型条件明确拆为三项：启用生成、填写TrueFoundry Gateway Token、确认本次外发。配置区默认展开，并提示百炼Key不能替代Gateway Token。
- 已按用户提供的成功调用示例接入Auto Routing Virtual Model `qdrant-truefoundry-demo/qdrant-truefoundry-demo`：使用`stream=True`逐步展示回答，并从原始响应读取`x-tfy-resolved-model`及`x-tfy-applied-rules`中的实际服务档位和判断原因。原直连模型入口仍可切回；该增量已通过语法检查及5项生成模块离线测试（含模拟SSE流、响应头和Token用量），尚未执行真实RAG模型调用。

交流中形成的关键调整：

- 项目从Qdrant单产品纯文本Demo，小步扩展到一份AI安全图文出差报告；来源仍明确区分，不把会议观点或厂商介绍当作Qdrant官方事实。
- 当前只采用“图片→Caption→文本向量”的方案。曾讨论为图片保留Caption向量和原图向量，但用户决定先调研百炼是否有合适的多模态Embedding模型，因此原图Embedding、双命名向量和以图搜图均暂缓。
- 图片解析直接调用百炼，不要求先经过TrueFoundry；文本回答生成仍保留为独立、可选的TrueFoundry入口。
- 保留已有纯文本流程，不进行工程重构，不自动递归抓取资料，也不把评价问题写入知识库。

## 2. 当前实现流程

### 文本与图片说明入库

```text
显式资料清单
→ 解析Markdown章节、FAQ、表格、代码块和图片引用
→ 普通正文切片
→ 读取已授权生成并缓存的图片Caption，形成独立图片说明片段
→ FastEmbed生成文本向量
→ 写入独立Qdrant Collection
```

原图不写入Qdrant。Qdrant保存正文或图片说明、文本向量和来源元数据；原图继续保留在本地。

### 查询与回答

```text
用户文字问题
→ BGE文本Embedding
→ Qdrant余弦相似度Top-K检索（可按来源类型过滤）
→ 展示片段、来源和关联原图
→ 可选：把问题和本次Top-K片段发给TrueFoundry生成带引用回答
```

回答模型只会看到预生成的图片说明，不会实时查看原图。相似度分数只表示向量接近程度，不是答案正确率。

## 3. 关键文件入口

| 文件 | 用途 |
|---|---|
| `README.md` | 当前范围、环境准备、启动方法和状态总览 |
| `app.py` | Streamlit三页界面、回答模型配置和来源/原图展示 |
| `ingest.py` | 切片预览、Embedding和Qdrant入库 |
| `analyze_images.py` | 图片清单刷新；只有带明确执行及授权参数时才调用视觉模型 |
| `knowledge_assistant/manifest.py` | 16份资料的唯一入库清单及来源状态 |
| `knowledge_assistant/preprocess.py` | 章节、FAQ、表格、代码块和图片说明切分 |
| `knowledge_assistant/images.py` | 图片引用、章节关联、路径白名单及哈希缓存 |
| `knowledge_assistant/vision.py` | 百炼OpenAI兼容视觉接口 |
| `knowledge_assistant/embedding.py` | 本地FastEmbed封装 |
| `knowledge_assistant/store.py` | Collection、增量更新、检索和过滤 |
| `knowledge_assistant/generation.py` | TrueFoundry流式生成、Auto Routing响应头、上下文组装和引用校验 |
| `docs/IMAGE_INGEST.md` | 图文接入实现、外发边界及验证状态 |
| `docs/AUTO_ROUTING_TEST.md` | 六条真实RAG测试、路由字段口径和人工记录表 |
| `docs/DEMO_SCRIPT.md` | 演示顺序 |
| `artifacts/image_descriptions.json` | 13张图片的Caption缓存，不含凭据 |
| `artifacts/chunk_preview.md` | 当前切片预览 |
| `evaluation_questions.json` / `image_evaluation_questions.json` | 文本及图文评价问题，不参与入库 |

## 4. 启动方式

建议使用已有环境：

```powershell
conda activate qdrant-poc
cd D:\SYJProject\HongKe\Demos\ai_product_knowledge_assistant
```

先启动本地Qdrant，并确认`http://127.0.0.1:6333`可访问。若当前终端继承了异常代理（此前代理曾指向`127.0.0.1:9`并造成502），先清除：

```powershell
Remove-Item Env:HTTP_PROXY -ErrorAction SilentlyContinue
Remove-Item Env:HTTPS_PROXY -ErrorAction SilentlyContinue
Remove-Item Env:ALL_PROXY -ErrorAction SilentlyContinue
$env:QDRANT_KB_URL = "http://127.0.0.1:6333"
```

预览、入库和启动页面：

```powershell
python ingest.py --preview-only
python ingest.py
streamlit run app.py
```

默认Collection：`ai_product_kb_qdrant_v01`。不应改动或删除其他实验Collection。

使用TrueFoundry生成回答时，在页面内完成三项配置：勾选启用、输入Gateway Token、确认本次资料外发。修改代码后应先停止旧Streamlit进程，再重新运行；页面出现“回答模型配置已就绪”后才进入真实调用。

## 5. 验证状态

### 已真实运行或有实际结果

- 原文本版Streamlit曾由用户成功启动并查看，用户确认页面整体效果可用。
- `BAAI/bge-small-zh-v1.5`本地缓存可用，实际输出维度为512。
- 原版曾用真实512维Embedding完成30个样例片段的Qdrant内存模式冒烟检查。
- 13张图片已真实发送至获授权的百炼视觉接口，`qwen3.7-flash`成功生成13份Caption，失败0张。
- 当前离线预处理实际得到330个正文片段和13个图片说明片段，共343个。

### 仅代码完成或离线检查通过

- 14项离线单元测试已通过，覆盖切分、图片关联、缓存、入库更新、过滤和引用处理等局部逻辑。
- Qdrant内存模式已验证重复入库跳过、资料变更替换和来源类型过滤；这不等同于当前6333服务器已完成持久化入库。
- 图片命中后的原图展示代码已完成；因343片段尚未写入当前本地服务器，真实图文召回、引用映射和原图命中展示尚未验收。
- TrueFoundry回答接口已改为流式Auto Routing调用，页面能展示请求模型、实际模型、实际服务档位、判断原因、上下文长度和可用Token用量；尚无本项目成功生成回答的确认记录。需由用户启动服务、输入Token并执行六条真实RAG问题。

### 当前未通过

- 交接前最近一次检查中，`127.0.0.1:6333`未监听，连接被拒绝；343个片段尚未持久化到本地Qdrant。
- 交接前没有正在监听的8501端口，因此当前页面也未处于运行状态。

## 6. 模型、检索与数据外发

| 环节 | 当前实现 | 数据位置或外发内容 |
|---|---|---|
| 文本Embedding | FastEmbed `BAAI/bge-small-zh-v1.5`，512维 | 本地运行，不外发文本 |
| 向量存储与检索 | 本地Qdrant，Cosine距离，单一文本向量 | 本地；正文和Caption进入独立Collection |
| 图片解析 | 百炼`qwen3.7-flash` | 已获授权外发13张原图、文档标题、章节和前后少量相邻正文；结果已缓存 |
| 回答生成 | TrueFoundry Gateway，默认Auto Routing ID为`qdrant-truefoundry-demo/qdrant-truefoundry-demo`，保留原直连入口 | 仅在用户当次勾选授权并输入Token后，发送问题与实际Top-K片段；请求日志按用户成功示例开启，尚未确认本项目真实调用成功 |

项目不保存、打印或归档API Key和Gateway Token。百炼侧、TrueFoundry侧是否记录请求内容取决于各自平台配置，代码不对此作保证。

## 7. 已知问题与未实现内容

- 本地Qdrant服务当前未运行；需先恢复6333服务，再执行完整入库。
- 系统代理可能导致对本地Qdrant请求返回502，启动前应检查并清除异常代理变量。
- TrueFoundry页面当前不从环境变量回退读取Token，需在当前Streamlit会话手工输入；云端Simple/Medium/Complex与`syj`、`qwen3.7-flash`、`syj2`的对应关系及控制台分类策略没有截图依据，本地不猜测。若三项均就绪仍失败，应记录页面显示的真实Gateway错误再定位。
- 图文评价问题尚未进行真实Top-K召回对比，不能把Caption成功等同于图文RAG验收通过。
- 当前没有原图Embedding、命名多向量、以图搜图、文本/图像融合排序或实时视觉问答。
- 没有TrueFoundry容灾、灰度或可观测性治理；这属于后续阶段，不应混入当前本地RAG验收。
- 没有自动飞书同步、权限系统、复杂对话记忆、Agent或多产品混合路由。
- `artifacts/tmp_zuwak7y`是早期测试留下的不可访问临时空目录，曾导致递归工具告警，但不影响应用主流程；无需围绕它重复排查。

## 8. 建议下一步

1. 启动本地Qdrant，清除异常代理后运行`python ingest.py`，确认16份资料、343个片段进入独立Collection。
2. 用`image_evaluation_questions.json`中的3～5个问题检查正文、图片说明及图文结合召回，并核对章节、引用和原图是否一一对应。
3. 重启Streamlit，确认回答配置区显示“回答模型配置已就绪”，再进行一次受控TrueFoundry真实生成；若失败，只记录实际错误，不改动本地检索基线。
4. 根据真实召回结果调整个别Caption或切片，而不是先引入复杂框架。
5. 用户完成百炼多模态Embedding模型调研后，再单独决定是否增加原图向量及命名多向量；新增前先确认模型、维度、费用、数据外发和融合检索方式。
