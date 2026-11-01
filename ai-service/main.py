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

# 进程内问题缓存（单实例足够；多实例应换 Redis）
_CACHE: dict = {}

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
                message = getattr(gen, "message", None)
                # 1.x 流式：usage_metadata（input_tokens/output_tokens）
                usage_meta = getattr(message, "usage_metadata", None) or {}
                if usage_meta:
                    self.usage = {
                        "prompt_tokens": usage_meta.get("input_tokens"),
                        "completion_tokens": usage_meta.get("output_tokens"),
                    }
                    continue
                meta = getattr(message, "response_metadata", {}) or {}
                usage = meta.get("token_usage") or meta.get("usage")
                if usage:
                    self.usage = {
                        "prompt_tokens": usage.get("prompt_tokens"),
                        "completion_tokens": usage.get("completion_tokens"),
                    }


SYSTEM_PROMPT = """你是 MallX 商城的在线客服「小 M」。
回答政策/规则类问题时，必须先调用 search_knowledge_base 检索知识库。
检索结果里如果已有答案，直接按原文回答，不要声称"没有检索到"；回答末尾必须标注来源，格式：【来源：文件名 · 小节】。
只有检索结果确实为空时，才说没有查到并建议转人工。
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
    from kb_lib import embed as _embed
    return {"status": "UP", "model": MODEL, "baseUrl": BASE_URL, "configured": bool(API_KEY),
            "embeddingMode": _embed.mode()}


@app.get("/kb/search")
def kb_search(q: str = Query(..., min_length=1), k: int = 4):
    return {"code": 200, "query": q, "chunks": store.search(q, k=k)}


@app.get("/conversations")
def conversations(user_id: int = 0):
    return {"code": 200, "items": memory.list_conversations(user_id)}


@app.get("/conversations/{conversation_id}/messages")
def conversation_messages(conversation_id: int, user_id: int = 0):
    rows = memory.get_messages(user_id, conversation_id)
    if rows is None:
        return {"code": 403, "message": "会话不存在或不属于当前用户"}
    return {"code": 200, "items": rows}


@app.get("/ai/stats")
def ai_stats():
    import psycopg2
    from kb_lib.memory import _conn
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FILTER (WHERE role = 'assistant'),
                   coalesce(sum(prompt_tokens), 0),
                   coalesce(sum(completion_tokens), 0),
                   round(coalesce(avg(elapsed_ms), 0)),
                   count(*) FILTER (WHERE role = 'assistant' AND refusal)
              FROM ai_messages
        """)
        calls, pt, ct, avg_ms, refusals = cur.fetchone()
        cur.execute("SELECT count(*) FROM ai_messages WHERE role='assistant' AND created_at >= CURRENT_DATE")
        today = cur.fetchone()[0]
    return {"code": 200, "calls": calls, "todayCalls": today, "promptTokens": pt,
            "completionTokens": ct, "avgElapsedMs": int(avg_ms or 0),
            "refusals": refusals, "refusalRate": round(refusals / calls, 3) if calls else 0}


@app.get("/kb/docs")
def kb_docs():
    return {"code": 200, "items": store.documents()}


@app.get("/kb/chunks")
def kb_chunks(source: str = Query(..., min_length=1)):
    return {"code": 200, "items": store.chunks_of(source)}


@app.post("/kb/rebuild")
def kb_rebuild():
    import os as _os
    base = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "kb")
    return {"code": 200, **store.ingest_dir(base)}


@app.post("/kb/upload")
def kb_upload(body: dict):
    name = (body.get("name") or "").strip()
    content = body.get("content") or ""
    if not name or not content.strip():
        return {"code": 400, "message": "文件名和内容不能为空"}
    saved = store.save_document(name, content)
    import os as _os
    base = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "kb")
    stats = store.ingest_dir(base)
    return {"code": 200, "saved": saved, **stats}


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
    # Day 117：同问题缓存（仅政策类、无用户身份依赖），省 token
    cache_key = f"{MODEL}|{message.strip()}"
    hit = _CACHE.get(cache_key)
    if hit and time.time() < hit["expire"]:
        memory.append(conv_id, message, hit["reply"], hit.get("tokens"), 0, False)
        return {**hit["payload"], "conversation_id": conv_id, "cached": True,
                "tokens": hit.get("tokens"), "elapsed_ms": 0}

    try:
        result = executor.invoke(
        {
            "input": message,
            "history": [(m.get("role"), m.get("content")) for m in history if m.get("content")],
        },
            config={"callbacks": [tracker]},
        )
    except Exception as exc:  # noqa: BLE001
        # Day 117：模型失败降级到「知识库原文 + 来源」，保证有依据而不是直接报错
        rows = store.search(message, k=1)
        if rows:
            top = rows[0]
            reply_text = f"根据知识库：\n{top['content']}\n【来源：{top['source']} · {top['heading']}】"
            memory.append(conv_id, message, reply_text, {}, int((time.time() - started) * 1000), False)
            return {"code": 200, "reply": reply_text, "tools": ["search_knowledge_base"],
                    "sources": [{"source": top["source"], "heading": top["heading"]}],
                    "elapsed_ms": int((time.time() - started) * 1000),
                    "conversation_id": conv_id, "tokens": {}, "grounded": True,
                    "refusal": False, "fallback": True, "reason": str(exc)[:200]}
        raise
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
    # Day 118：给来源补一句可展示的原文片段
    if sources:
        rows_by_key = {(r["source"], r["heading"]): r["content"] for r in store.search(message, k=20)}
        for s in sources:
            s["snippet"] = rows_by_key.get((s["source"], s["heading"]), "")[:120]

    reply_text = result.get("output", "")
    # Day 114：引用必须来自本轮检索结果；政策类问题没检索到可靠依据时拒答
    retrieved = {(s["source"], s["heading"]) for s in sources}
    cited_pairs = [(m.group(1).strip(), (m.group(2) or "").strip())
                   for m in re.finditer(r"【来源：([^·】]+)(?: · ([^】]+))?】", reply_text)]
    invalid_refs = [p for p in cited_pairs if p not in retrieved]
    refusal = False
    policy_words = ("运费", "退款", "退货", "售后", "优惠券", "发票", "发货", "支付", "拆单", "取消订单")
    is_policy = any(w in message for w in policy_words)
    has_citation = bool(cited_pairs)
    if invalid_refs or (is_policy and not sources):
        reply_text = "抱歉，这个问题我暂时没找到可靠的知识库依据。你可以换个说法，或到「个人中心」查看订单详情，必要时转人工客服。"
        sources = []
        refusal = True
    elif not sources and any(w in reply_text for w in ("抱歉", "不在我的服务范围", "无法回答", "只能帮")):
        refusal = True
    elif is_policy and sources and not has_citation:
        # 模型没给引用：用它检索到的第一条原文兜底，保证"有依据"而不是自由发挥
        rows = store.search(message, k=1)
        if rows:
            top = rows[0]
            reply_text = f"根据知识库：\n{top['content']}\n【来源：{top['source']} · {top['heading']}】"
        refusal = False
    memory.append(conv_id, message, reply_text, tracker.usage, elapsed_ms, refusal)
    if is_policy and not refusal:
        _CACHE[cache_key] = {
            "expire": time.time() + 600,
            "reply": reply_text,
            "tokens": tracker.usage,
            "payload": {"code": 200, "reply": reply_text, "tools": used,
                        "sources": sources, "grounded": True, "refusal": False},
        }
    return {
        "code": 200,
        "reply": reply_text,
        "tools": used,
        "sources": sources,
        "grounded": bool(sources) and not invalid_refs and not refusal,
        "refusal": refusal,
        "elapsed_ms": elapsed_ms,
        "conversation_id": conv_id,
        "tokens": tracker.usage,
    }
