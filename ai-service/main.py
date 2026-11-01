"""MallX AI 客服（Python · FastAPI + LangChain）.

职责边界：
- 本服务只做「模型编排 + 工具调用」，业务数据一律回查 Java（商品/订单/售后接口）；
- 用户身份来自调用方透传的 Authorization 头，工具不会接受「查谁」参数；
- 无 OPENAI_API_KEY 时不启动模型调用（Java 侧会自动回退到 mock），/chat 返回 503。

启动：uvicorn main:app --host 127.0.0.1 --port 8008
"""
import os
import re
import time
from typing import List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, Query

# ★ 本地密钥放 ai-service/.env（已被 .gitignore 排除），不要提交到仓库
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from kb_lib import memory, store

app = FastAPI(title="MallX AI Service", version="1.0.0")

JAVA_BASE = os.getenv("JAVA_BASE_URL", "http://127.0.0.1:8081")
MODEL = os.getenv("OPENAI_MODEL", "deepseek-chat")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
API_KEY = os.getenv("OPENAI_API_KEY", "")

class UsageTracker(BaseCallbackHandler):
    """收集 OpenAI 返回的 token 用量；流式下由 stream_usage=True 提供。"""

    def __init__(self):
        self.usage = {}

    def on_llm_end(self, response, **kwargs):
        for generations in response.generations:
            for gen in generations:
                meta = getattr(getattr(gen, "message", None), "response_metadata", {}) or {}
                usage = meta.get("token_usage") or meta.get("usage")
                if usage:
                    self.usage = {
                        "prompt_tokens": usage.get("prompt_tokens"),
                        "completion_tokens": usage.get("completion_tokens"),
                    }


SYSTEM_PROMPT = """你是 MallX 商城的在线客服「小 M」。
回答政策/规则类问题时，先调用 search_knowledge_base 检索知识库，并在回答末尾标注来源，格式：【来源：文件名 · 小节】。
只回答商品咨询、订单状态、售后进度；不编造订单号/金额/物流，不承诺未发生的事。
涉及用户数据时必须调用工具，禁止根据提问内容猜测。"""


def _build_tools(token: Optional[str]):
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    @tool
    def search_knowledge_base(query: str) -> str:
        """检索 MallX 的规则与政策知识库（运费、退换货、支付、优惠券、账号等）。"""
        rows = store.search(query, k=4)
        if not rows:
            return "知识库没有相关内容，请转人工或让用户查看订单详情"
        return "\n\n".join(
            f"【来源：{r['source']} · {r['heading']}】\n{r['content']}" for r in rows
        )

    @tool
    def search_products(keyword: str) -> str:
        """按关键词搜索在售商品，返回名称、价格与 id。"""
        with httpx.Client(timeout=8) as c:
            r = c.get(f"{JAVA_BASE}/api/products",
                      params={"keyword": keyword, "current": 1, "size": 5})
        data = r.json().get("data") or {}
        rows = data.get("records") or []
        if not rows:
            return "没有搜到相关商品"
        return "\n".join(f"{p['name']}（¥{p.get('minPrice') or p.get('price')}）" for p in rows)

    @tool
    def my_orders() -> str:
        """查询当前登录用户自己的订单列表（无需参数）。"""
        if not headers:
            return "用户未登录，无法查询订单"
        with httpx.Client(timeout=8) as c:
            r = c.get(f"{JAVA_BASE}/api/orders", params={"page": 1, "size": 5}, headers=headers)
        data = r.json().get("data") or {}
        rows = data.get("records") or []
        if not rows:
            return "当前没有订单"
        return "\n".join(f"订单 {o.get('orderNo')}：{o.get('status')}，应付 ¥{o.get('payAmount')}" for o in rows)

    @tool
    def my_refunds() -> str:
        """查询当前登录用户自己的售后/退款进度（无需参数）。"""
        if not headers:
            return "用户未登录，无法查询售后"
        with httpx.Client(timeout=8) as c:
            r = c.get(f"{JAVA_BASE}/api/refunds/my", params={"page": 1, "size": 5}, headers=headers)
        data = r.json().get("data") or {}
        rows = data.get("records") or []
        if not rows:
            return "当前没有售后记录"
        return "\n".join(f"售后 #{x.get('id')}：{x.get('status')}，订单 {x.get('orderNo')}" for x in rows)

    return [search_knowledge_base, search_products, my_orders, my_refunds]


@app.get("/health")
def health():
    return {"status": "UP", "model": MODEL, "baseUrl": BASE_URL, "configured": bool(API_KEY)}


@app.get("/kb/search")
def kb_search(q: str = Query(..., min_length=1), k: int = 4):
    return {"code": 200, "query": q, "chunks": store.search(q, k=k)}


@app.get("/kb/stats")
def kb_stats():
    return {"code": 200, **store.stats(), **memory.stats()}


@app.post("/chat")
def chat(body: dict, authorization: Optional[str] = Header(default=None)):
    if not API_KEY:
        return {"code": 503, "message": "AI_API_KEY 未配置"}
    token = authorization.split(" ", 1)[-1] if authorization else None
    message = (body.get("message") or "").strip()
    history: List[dict] = body.get("history") or []
    conversation_id = body.get("conversation_id")
    user_id = body.get("user_id")
    conv_id = memory.ensure_conversation(user_id, conversation_id)
    db_history = memory.history(conv_id)
    if db_history:
        history = db_history

    llm = ChatOpenAI(
        model=MODEL, base_url=BASE_URL, api_key=API_KEY, temperature=0.3, timeout=20,
        stream_usage=True,
    )
    tools = _build_tools(token)
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder("history"),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])
    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(
        agent=agent, tools=tools, max_iterations=3, verbose=False, return_intermediate_steps=True,
    )
    started = time.time()
    tracker = UsageTracker()
    result = executor.invoke(
        {
            "input": message,
            "history": [(m.get("role"), m.get("content")) for m in history if m.get("content")],
        },
        config={"callbacks": [tracker]},
    )
    elapsed_ms = int((time.time() - started) * 1000)
    steps = result.get("intermediate_steps", [])
    used = [step[0].tool for step in steps]
    sources, seen = [], set()
    for step in steps:
        if step[0].tool != "search_knowledge_base":
            continue
        for m in re.finditer(r"【来源：([^·】]+)(?: · ([^】]+))?】", str(step[1])):
            key = (m.group(1).strip(), (m.group(2) or "").strip())
            if key in seen:
                continue
            seen.add(key)
            sources.append({"source": key[0], "heading": key[1]})
    memory.append(conv_id, message, result.get("output", ""), tracker.usage)
    return {
        "code": 200,
        "reply": result.get("output", ""),
        "tools": used,
        "sources": sources,
        "elapsed_ms": elapsed_ms,
        "conversation_id": conv_id,
        "tokens": tracker.usage,
    }
