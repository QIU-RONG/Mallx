"""知识库存储与检索（Day 109）。

表结构由 Java 侧迁移 backend/sql/26-ai-knowledge.sql 创建；
这里只做 ingest / search，不负责业务数据。
"""
import hashlib
import math
import os
import time

import psycopg2
import psycopg2.extras

from . import embed as embedder

DB = dict(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "5434")),
    dbname=os.getenv("DB_NAME", "mallx"),
    user=os.getenv("DB_USERNAME", "mallx"),
    password=os.getenv("DB_PASSWORD", "mallx123"),
)

_CACHE = {"at": 0.0, "rows": []}
_CACHE_TTL = 30


def _conn():
    return psycopg2.connect(**DB)


def _chunk_document(source: str, text: str, size: int = 420, overlap: int = 80):
    """按二级标题切段，再按长度滑窗，保留 heading 便于引用。"""
    chunks = []
    heading = ""
    block = []
    for line in text.splitlines():
        if line.startswith("## "):
            if block:
                chunks.extend(_split(source, heading, "\n".join(block), size, overlap))
                block = []
            heading = line[3:].strip()
        elif line.startswith("# "):
            continue
        else:
            block.append(line)
    if block:
        chunks.extend(_split(source, heading, "\n".join(block), size, overlap))
    return chunks


def _split(source: str, heading: str, body: str, size: int, overlap: int):
    body = body.strip()
    if not body:
        return []
    out = []
    start = 0
    while start < len(body):
        piece = body[start:start + size].strip()
        if piece:
            out.append({"source": source, "heading": heading, "content": piece})
        if start + size >= len(body):
            break
        start += size - overlap
    return out


def ingest_dir(path: str) -> dict:
    files = sorted(f for f in os.listdir(path) if f.endswith(".md"))
    total = 0
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ai_kb_chunks")
        for name in files:
            text = open(os.path.join(path, name), encoding="utf-8").read()
            chunks = _chunk_document(name, text)
            if not chunks:
                continue
            vectors = embedder.embed([c["content"] for c in chunks])
            rows = [
                (c["source"], c["heading"], c["content"], v)
                for c, v in zip(chunks, vectors)
            ]
            psycopg2.extras.execute_batch(
                cur,
                "INSERT INTO ai_kb_chunks (source, heading, content, embedding) VALUES (%s, %s, %s, %s)",
                rows,
            )
            total += len(rows)
    _CACHE["at"] = 0.0
    return {"files": len(files), "chunks": total}


def _load_rows():
    now = time.time()
    if _CACHE["rows"] and now - _CACHE["at"] < _CACHE_TTL:
        return _CACHE["rows"]
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, source, heading, content, embedding FROM ai_kb_chunks")
        rows = [
            {"id": r[0], "source": r[1], "heading": r[2], "content": r[3], "embedding": r[4]}
            for r in cur.fetchall()
        ]
    _CACHE.update(at=now, rows=rows)
    return rows


def _cos(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def search(query: str, k: int = 4, min_score: float = 0.05) -> list[dict]:
    rows = _load_rows()
    if not rows:
        return []
    qv = embedder.embed([query])[0]
    scored = []
    for r in rows:
        score = _cos(qv, list(r["embedding"]))
        if score >= min_score:
            scored.append({
                "id": r["id"],
                "source": r["source"],
                "heading": r["heading"],
                "content": r["content"],
                "score": round(score, 4),
            })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:k]


def stats() -> dict:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*), count(DISTINCT source) FROM ai_kb_chunks")
        n, files = cur.fetchone()
    return {"chunks": n, "files": files}


def fingerprint() -> str:
    rows = _load_rows()
    h = hashlib.md5()
    for r in rows:
        h.update((r["content"] or "").encode("utf-8"))
    return h.hexdigest()[:12]
