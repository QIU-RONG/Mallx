# Day 125 · WSL2 + pgvector 落地（真实向量库）

## 安装（方案 B）

- WSL Ubuntu 26.04 自带 PostgreSQL 18（5433）；
- `apt install postgresql-18-pgvector` → `share/extension/vector.control` 就绪；
- 建 `mallx` 角色/库，跑 `backend/sql/01–29`；迁移 29 检测到扩展，自动建
  `embedding_vec vector(512)` + ivfflat 索引。

## 代码

- `store.ingest_dir()`：检测到 pgvector 时同时写 `embedding`（real[]，兜底）与 `embedding_vec`（512 维）；
- `store.search()`：有 pgvector 时先用 `ORDER BY embedding_vec <=> %s::vector LIMIT 20` 召回，
  再用「余弦 + 字面 bigram」混合重排；扩展/维度不匹配时自动回退 Python 余弦；
- 本地模型 ONNX 在内存紧张时会 `bad allocation`，已支持 `EMBEDDING_THREADS=1`，
  并在入库时临时停掉前端/后端释放提交内存。

## 验证

- `ai_kb_chunks`：**20/20 行 embedding_vec 非空**；
- 检索评测（走 pgvector 召回 + 混合重排）：**hit@1 46/50、hit@4 50/50**；
- 服务切到 5433：8081 health UP、AI `embeddingMode=local`、
  `/api/ai/chat` 返回 `mode=langchain` + 4 条来源；5173/5174 正常。

## 注意

- WSL 会在最后一个进程退出后关停：需要一个常驻进程（本次用 `sleep infinity`）保持 5433 可达；
- 原 Windows 5434 的旧库保留未迁移，回滚只需把 `DB_PORT` 改回 5434。
