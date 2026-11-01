# MallX AI Service（FastAPI + LangChain）

Python 侧的 AI 客服编排，业务数据仍回查 Java 后端的 C 端接口。

## 启动

```bash
cd ai-service
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt       # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS/Linux

export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://api.deepseek.com/v1   # 任意 OpenAI 兼容网关
export OPENAI_MODEL=deepseek-chat
export JAVA_BASE_URL=http://127.0.0.1:8081
uvicorn main:app --host 127.0.0.1 --port 8008
```

Java 侧设置 `AI_SERVICE_URL=http://127.0.0.1:8008` 后，`/api/ai/chat` 会转发到本服务；
不设置时仍走 Java 内置的 LangChain4j 或 mock。

## 接口

- `GET /health`：是否配置了 key、模型与上游地址；
- `POST /chat`：`{message, history:[{role,content}]}` + `Authorization` 头（可选，登录用户才带）。

工具（`search_products` / `my_orders` / `my_refunds`）通过 `httpx` 调 Java：
`/api/products`、`/api/orders`、`/api/refunds/my`；用户身份由 Authorization 透传，
工具参数里没有 userId —— 模型无法指定查别人的数据。

## 说明

- 模型不可用（无 key）时 `/chat` 返回 503，Java 侧按调用失败处理并给出兜底文案；
- 迭代上限 3 轮（`max_iterations`），与 Java 版 `max-tool-rounds` 同口径；
- 依赖版本锁定在 `requirements.txt`。

## API Key 放哪里

复制 `ai-service/.env.example` 为 `ai-service/.env`，把真实 key 填进 `OPENAI_API_KEY`。
`.env` 已被 `.gitignore` 排除，不要提交；服务启动时会自动加载（python-dotenv）。
Java 侧只需配置 `AI_SERVICE_URL`，不再需要 `AI_API_KEY`。
