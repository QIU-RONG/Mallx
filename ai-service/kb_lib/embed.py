"""Embedding 适配层（Day 109）。

有 EMBEDDING_API_KEY / OPENAI_API_KEY 时调 OpenAI 兼容 /embeddings；
没有时用确定性哈希向量（按字符 bigram + md5），保证离线可跑、评测可复现。
"""
import hashlib
import math
import os

import httpx

DIM = 384
API_KEY = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
BASE_URL = os.getenv("EMBEDDING_BASE_URL") or os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")


def _hash_embed(text: str) -> list[float]:
    vec = [0.0] * DIM
    grams = [text[i:i + 2] for i in range(max(1, len(text) - 1))]
    for g in grams:
        h = hashlib.md5(g.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "big") % DIM
        sign = 1.0 if h[4] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def mode() -> str:
    return "remote" if API_KEY else "hash"


def embed(texts: list[str]) -> list[list[float]]:
    """批量取向量；失败时退回哈希向量，保证检索链路不中断。"""
    if API_KEY:
        try:
            with httpx.Client(timeout=20) as c:
                r = c.post(
                    f"{BASE_URL.rstrip('/')}/embeddings",
                    headers={"Authorization": f"Bearer {API_KEY}"},
                    json={"model": EMBED_MODEL, "input": texts},
                )
                r.raise_for_status()
                return [row["embedding"] for row in r.json()["data"]]
        except Exception as exc:  # noqa: BLE001
            print(f"[embed] 远程向量失败，改用哈希向量：{exc}")
    return [_hash_embed(t) for t in texts]
