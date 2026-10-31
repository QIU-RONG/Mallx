# Day 107 · AI 客服改用 LangChain4j

把原来手写的「LLM 请求 + tool_calls 循环」换成 LangChain4j（1.3.0）：

- 依赖：langchain4j + langchain4j-open-ai（同一版本 1.3.0）；
- LangChainService：用 OpenAiChatModel（apiKey / baseUrl / modelName / timeout 来自 mallx.ai），
  缓存一个模型实例；每次请求用 AiServices.builder(...).tools(...) 构建一次 assistant；
- LangChainTools：@Tool 暴露 searchProducts / myOrders / myRefunds，
  **userId 由构造注入，工具签名没有 userId**（模型无法查别人），并记录本轮用到的工具名；
- LangChainAssistant：@SystemMessage 定义客服口径，@UserMessage 收问题；
  历史对话拼成「对话历史 + 当前问题」一次性传入；
- AiChatServiceImpl#viaLlm 现在只负责注入身份与包装免责声明，工具循环交给 LangChain4j；
- **无 key 仍然走原来的 mock（规则 + 模板 + 真实查库）**，行为不变；有 key 才走模型。

## 验证

- 起了一个假 OpenAI 服务（127.0.0.1:8099），用 AI_API_KEY=test-key、AI_BASE_URL=http://127.0.0.1:8099/v1 启动第二个实例：
  POST /api/ai/chat 返回 mode=llm，正文为假模型固定回答 —— 证明 LangChain4j 的模型调用链通了；
- 默认实例（无 key）仍返回 mode=mock、工具 search_products，主链路 e2e 40/40；
- 前端无需改动（响应结构不变：reply / mode / tools）。
