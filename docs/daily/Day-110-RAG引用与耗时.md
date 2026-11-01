# Day 110 · RAG 引用来源与耗时透传

- Python /chat 新增返回：
  - sources：从 search_knowledge_base 工具结果里解析 【来源：文件 · 小节】 并去重；
  - elapsed_ms：本轮 Agent 编排耗时；
  - 修正 AgentExecutor(return_intermediate_steps=True)，否则工具调用记录为空（第一版就踩了）；
- Java AiChatReply 增加 sources / elapsedMs，AiServiceClient 解析透传；
- SSE 的 done 事件同步携带 sources、elapsedMs（前端流式结束即可展示）；
- C 端 AI 组件：助手消息下展示来源胶囊（文件 · 小节）与耗时，mock 模式不展示；
- 前端类型同步扩展 AiChatReply。

## 验证

- Python /chat（假模型带 tool_calls）返回 	ools=[search_knowledge_base]、4 条来源、elapsed_ms≈310；
- Java 8082（AI_SERVICE_URL 指向 Python）/api/ai/chat 返回 mode=langchain、	ools 含检索工具、
  elapsedMs=241、4 条 sources —— 全链路打通；
- 前端 lint/build 通过；默认 8081（mock）e2e 40/40。
