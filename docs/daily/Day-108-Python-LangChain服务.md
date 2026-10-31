# Day 108 · Python AI 服务（FastAPI + LangChain）

按「Java 只转发、模型与工具在 Python」的分工落地：

## ai-service/

- main.py：FastAPI，GET /health + POST /chat；
- 依赖：langchain 0.3.25 + langchain-openai 0.3.7（锁定在 requirements.txt）；
- 编排：create_tool_calling_agent + AgentExecutor(max_iterations=3)，提示词定义客服口径；
- 工具（@tool）用 httpx 回查 Java：
  - search_products → GET /api/products?keyword=...
  - my_orders → GET /api/orders（带 Authorization）
  - my_refunds → GET /api/refunds/my（带 Authorization）
- 用户身份来自 Java 透传的 Authorization，工具参数没有 userId；
- 无 OPENAI_API_KEY 时 /chat 返回 503。

## Java 侧

- mallx.ai.service-url（AI_SERVICE_URL）非空时，AiChatServiceImpl 走 AiServiceClient 转发到 Python；
  否则保持原逻辑（LangChain4j → mock）；
- AiServiceClient 用 java.net.http.HttpClient POST /chat，从当前请求取 Authorization 原样透传；
- 响应结构不变（reply / mode / tools），mode=langchain，前端无需改动。

## 验证

- 假 OpenAI 服务（支持流式 chunk）→ Python /chat 返回固定回答；
- Java（AI_API_KEY 非空 + AI_SERVICE_URL=http://127.0.0.1:8008）POST /api/ai/chat 返回
  mode=langchain 与同一段文字，证明 Java → Python → 模型整条链路打通；
- 默认实例（无 service-url、无 key）仍是 mock，e2e 40/40 基线不变。
