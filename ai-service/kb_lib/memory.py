"""会话记忆（Day 111）。

按 Java 传下来的 user_id + conversation_id 持久化多轮对话；
Python 侧自己维护历史，前端刷新后只要带着 conversation_id 就能续上。
"""
import os

import psycopg2

DB = dict(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "5434")),
    dbname=os.getenv("DB_NAME", "mallx"),
    user=os.getenv("DB_USERNAME", "mallx"),
    password=os.getenv("DB_PASSWORD", "mallx123"),
)


def _conn():
    return psycopg2.connect(**DB)


def ensure_conversation(user_id: int | None, conversation_id: int | None) -> int:
    with _conn() as conn, conn.cursor() as cur:
        if conversation_id:
            cur.execute("SELECT id FROM ai_conversations WHERE id = %s", (conversation_id,))
            row = cur.fetchone()
            if row:
                return row[0]
        cur.execute(
            "INSERT INTO ai_conversations (user_id) VALUES (%s) RETURNING id",
            (user_id,),
        )
        return cur.fetchone()[0]


def history(conversation_id: int, limit: int = 10) -> list[dict]:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT role, content FROM ai_messages WHERE conversation_id = %s ORDER BY id DESC LIMIT %s",
            (conversation_id, limit),
        )
        rows = cur.fetchall()[::-1]
    return [{"role": r, "content": c} for r, c in rows]


def append(conversation_id: int, user_text: str, reply: str, tokens: dict | None = None) -> None:
    tokens = tokens or {}
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ai_messages (conversation_id, role, content, prompt_tokens, completion_tokens)"
            " VALUES (%s, 'user', %s, NULL, NULL)",
            (conversation_id, user_text),
        )
        cur.execute(
            "INSERT INTO ai_messages (conversation_id, role, content, prompt_tokens, completion_tokens)"
            " VALUES (%s, 'assistant', %s, %s, %s)",
            (conversation_id, reply, tokens.get("prompt_tokens"), tokens.get("completion_tokens")),
        )
        cur.execute("UPDATE ai_conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = %s", (conversation_id,))


def stats() -> dict:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM ai_conversations")
        convs = cur.fetchone()[0]
        cur.execute("SELECT count(*), coalesce(sum(prompt_tokens),0), coalesce(sum(completion_tokens),0) FROM ai_messages")
        msgs, pt, ct = cur.fetchone()
    return {"conversations": convs, "messages": msgs, "promptTokens": pt, "completionTokens": ct}
