"""Embedding 适配层（Day 109）。

有 EMBEDDING_API_KEY / OPENAI_API_KEY 时调 OpenAI 兼容 /embeddings；
没有时用确定性哈希向量（按字符 bigram + md5），保证离线可跑、评测可复现。
"""
import hashlib
import math
import os

import httpx
from dotenv import load_dotenv

# 本地脚本（ingest/eval）也要读到 .env，与服务进程同一套配置
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

DIM = 384
# EMBEDDING_MODE=hash 可强制离线哈希向量（本机默认，避免每次请求先试远程再降级）
MODE = os.getenv("EMBEDDING_MODE", "auto").lower()
LOCAL_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
_LOCAL_MODEL = None
API_KEY = "" if MODE == "hash" else (os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY") or "")
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
    if MODE == "local":
        return "local"
    if MODE == "hash":
        return "hash"
    return "remote" if API_KEY else "hash"


def _local(texts: list[str]) -> list[list[float]]:
    global _LOCAL_MODEL
    if _LOCAL_MODEL is None:
        from fastembed import TextEmbedding
        _LOCAL_MODEL = TextEmbedding(model_name=LOCAL_MODEL_NAME)
    return [[float(x) for x in v] for v in _LOCAL_MODEL.embed(texts)]


def embed(texts: list[str]) -> list[list[float]]:
    """批量取向量；失败时退回哈希向量，保证检索链路不中断。"""
    if MODE == "local":
        try:
            return _local(texts)
        except Exception as exc:  # noqa: BLE001
            print(f"[embed] 本地模型失败，改用哈希向量：{exc}")
            return [_hash_embed(t) for t in texts]
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
