# TrueFoundry Auto Routing验证记录

## 已确认配置

- Gateway：`https://gateway.truefoundry.ai`
- Virtual Model完整调用ID：`qdrant-truefoundry-demo/qdrant-truefoundry-demo`
- 路由方式：Auto Routing。
- 三个控制台目标显示名：`syj`、`qwen3.7-flash`、`syj2`。

当前没有可追溯截图说明三个目标分别对应Simple、Medium、Complex中的哪一档，也没有证据确认分类策略是Heuristic还是LLM Classification。因此不在本地文档中猜测映射。真实请求以`x-tfy-applied-rules`和`x-tfy-resolved-model`为准；若`syj`和`syj2`最终解析到相同底层模型，本实验只能验证路由过程，不能证明质量或成本分层。

## 运行原则

- 每个问题都从知识问答页发起，先经过本地Embedding与Qdrant检索，再把问题和Top-K片段交给Virtual Model。
- 页面每次只发送系统提示和当前单轮问题，不附加历史会话，避免历史固定档位影响比较。
- Auto Routing分类的是实际发送请求，包含系统提示、问题和召回上下文。技术词、上下文长度、会话固定、升级或回退都可能影响最终服务档位；不预设某题必须进入某一档。
- 页面显示的“引用状态”只检查是否存在映射到召回结果的有效编号。答案内容是否正确支持该引用仍需人工核对。

## 六条问题

详细预期要点及参考资料见`auto_routing_test_questions.json`。建议依次测试：

1. AR01、AR02：简单查找。
2. AR03、AR04：资料归纳。
3. AR05、AR06：综合比较。

不要为了制造档位差异临时改变问题。若六题全部进入同一档，先记录实际上下文长度、技术词密度和控制台分类策略，再判断是否符合当前策略。

## 真实运行记录

由人工运行后填写，不预填结果：

| 编号 | Top-K | 检索上下文字符数 | 实际服务档位 | 判断原因 | 实际服务模型 | 有效引用 | 人工核对结论 |
|---|---:|---:|---|---|---|---|---|
| AR01 |  |  |  |  |  |  |  |
| AR02 |  |  |  |  |  |  |  |
| AR03 |  |  |  |  |  |  |  |
| AR04 |  |  |  |  |  |  |  |
| AR05 |  |  |  |  |  |  |  |
| AR06 |  |  |  |  |  |  |  |

## 响应字段口径

- 请求模型：页面实际传入的Virtual Model或直连模型ID。
- 实际服务模型：`x-tfy-resolved-model`。
- 实际服务档位、判断原因：`x-tfy-applied-rules`中的`complexity.tier`和`complexity.cause`。
- 生成耗时：应用从发起请求到完整消费响应流的时间。
- Token用量：仅在流式响应实际返回usage时展示，否则显示“未返回”。

官方参考：<https://www.truefoundry.com/docs/ai-gateway/complexity-based-routing>
