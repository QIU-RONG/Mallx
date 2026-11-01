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
    """★ 越权防护：只复用「属于当前用户」的会话；别人的 id 一律新开会话。

    匿名用户（user_id 为空或 0）不复用任何历史会话，避免猜 id 读到别人的上下文。
    """
    uid = user_id or 0
    with _conn() as conn, conn.cursor() as cur:
        if conversation_id and uid:
            cur.execute(
                "SELECT id FROM ai_conversations WHERE id = %s AND user_id = %s",
                (conversation_id, uid),
            )
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


def append(conversation_id: int, user_text: str, reply: str, tokens: dict | None = None,
           elapsed_ms: int | None = None, refusal: bool = False) -> None:
    tokens = tokens or {}
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ai_messages (conversation_id, role, content, prompt_tokens, completion_tokens)"
            " VALUES (%s, 'user', %s, NULL, NULL)",
            (conversation_id, user_text),
        )
        cur.execute(
            "INSERT INTO ai_messages (conversation_id, role, content, prompt_tokens, completion_tokens,"
            " elapsed_ms, refusal) VALUES (%s, 'assistant', %s, %s, %s, %s, %s)",
            (conversation_id, reply, tokens.get("prompt_tokens"), tokens.get("completion_tokens"),
             elapsed_ms, refusal),
        )
        cur.execute("UPDATE ai_conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = %s", (conversation_id,))


def stats() -> dict:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM ai_conversations")
        convs = cur.fetchone()[0]
        cur.execute("SELECT count(*), coalesce(sum(prompt_tokens),0), coalesce(sum(completion_tokens),0) FROM ai_messages")
        msgs, pt, ct = cur.fetchone()
    return {"conversations": convs, "messages": msgs, "promptTokens": pt, "completionTokens": ct}

def list_conversations(user_id: int | None, limit: int = 20) -> list[dict]:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT c.id, c.updated_at,
                   (SELECT content FROM ai_messages m WHERE m.conversation_id = c.id AND m.role='user' ORDER BY m.id LIMIT 1) AS title,
                   (SELECT count(*) FROM ai_messages m WHERE m.conversation_id = c.id) AS msg_count
              FROM ai_conversations c
             WHERE c.user_id = %s
             ORDER BY c.updated_at DESC
             LIMIT %s
        """, (user_id or 0, limit))
        rows = cur.fetchall()
    return [{"id": r[0], "updatedAt": r[1].isoformat(sep=' ', timespec='seconds'),
             "title": (r[2] or "新会话")[:40], "messageCount": r[3]} for r in rows]


def get_messages(user_id: int | None, conversation_id: int) -> list[dict] | None:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT user_id FROM ai_conversations WHERE id = %s", (conversation_id,))
        row = cur.fetchone()
        if not row or row[0] != (user_id or 0):
            return None
        cur.execute("SELECT role, content, created_at FROM ai_messages WHERE conversation_id = %s ORDER BY id",
                    (conversation_id,))
        return [{"role": r[0], "content": r[1], "createdAt": r[2].isoformat(sep=' ', timespec='seconds')}
                for r in cur.fetchall()]
