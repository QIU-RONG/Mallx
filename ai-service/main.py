"""MallX AI 客服（Python · FastAPI + LangChain）.

职责边界：
- 本服务只做「模型编排 + 工具调用」，业务数据一律回查 Java（商品/订单/售后接口）；
- 用户身份来自调用方透传的 Authorization 头，工具不会接受「查谁」参数；
- 无 OPENAI_API_KEY 时不启动模型调用（Java 侧会自动回退到 mock），/chat 返回 503。

启动：uvicorn main:app --host 127.0.0.1 --port 8008
"""
import os
from typing import List, Optional

import httpx
from fastapi import FastAPI, Header
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

app = FastAPI(title="MallX AI Service", version="1.0.0")

JAVA_BASE = os.getenv("JAVA_BASE_URL", "http://127.0.0.1:8081")
MODEL = os.getenv("OPENAI_MODEL", "deepseek-chat")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
API_KEY = os.getenv("OPENAI_API_KEY", "")

SYSTEM_PROMPT = """你是 MallX 商城的在线客服「小 M」。
只回答商品咨询、订单状态、售后进度；不编造订单号/金额/物流，不承诺未发生的事。
涉及用户数据时必须调用工具，禁止根据提问内容猜测。"""


def _build_tools(token: Optional[str]):
    headers = {"Authorization": f"Bearer {token}"} if token else {}

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

    return [search_products, my_orders, my_refunds]


@app.get("/health")
def health():
    return {"status": "UP", "model": MODEL, "baseUrl": BASE_URL, "configured": bool(API_KEY)}


@app.post("/chat")
def chat(body: dict, authorization: Optional[str] = Header(default=None)):
    if not API_KEY:
        return {"code": 503, "message": "AI_API_KEY 未配置"}
    token = authorization.split(" ", 1)[-1] if authorization else None
    message = (body.get("message") or "").strip()
    history: List[dict] = body.get("history") or []

    llm = ChatOpenAI(model=MODEL, base_url=BASE_URL, api_key=API_KEY, temperature=0.3, timeout=20)
    tools = _build_tools(token)
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder("history"),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])
    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, max_iterations=3, verbose=False)
    result = executor.invoke({
        "input": message,
        "history": [(m.get("role"), m.get("content")) for m in history if m.get("content")],
    })
    used = [step[0].tool for step in result.get("intermediate_steps", [])]
    return {"code": 200, "reply": result.get("output", ""), "tools": used}
