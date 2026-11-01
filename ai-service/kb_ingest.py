"""知识库入库脚本（Day 109）。

用法：cd ai-service && .venv/Scripts/python.exe kb_ingest.py
"""
import os

from kb_lib import store

if __name__ == "__main__":
    base = os.path.join(os.path.dirname(__file__), "kb")
    result = store.ingest_dir(base)
    print(result)
