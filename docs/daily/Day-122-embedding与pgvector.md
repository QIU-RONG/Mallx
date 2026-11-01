# Day 122 · 真实 embedding 配置与 pgvector 可选迁移（环境受限）

## 已完成

- `embed.py` 支持独立 `EMBEDDING_BASE_URL`（不再强制和对话模型同网关）；
- `/health` 增加 `embeddingMode`（remote/hash），一眼看出当前检索用哪种向量；
- 迁移 29：**有 pgvector 时**自动建 `vector(384)` 列 + ivfflat 索引；没有时只打 NOTICE 跳过，不影响现有 real[] 方案。

## 环境现实（为什么没真正切过去）

- 本机 PostgreSQL（D:\PSQL）**没有安装 pgvector**：`pg_available_extensions` 查不到 `vector`，
  `share/extension` 下也没有 `vector.control`；装它需要编译扩展（MSVC + PG 头文件），不在本轮范围内；
- 没有 embedding 供应商 key（DeepSeek 不提供 embeddings 接口），真实向量调用无法实测；
- 因此当前仍是 **hash 向量 + real[] + Python 余弦**，属于有意的降级方案。

## 验证

- 迁移 29 执行成功：扩展不可用时跳过，`ai_kb_chunks=20` 不变；
- `/health` 返回 `embeddingMode=hash`（未配 key 时的诚实值）；
- 配置 `EMBEDDING_API_KEY` + `EMBEDDING_BASE_URL` 后重启即可切 remote（代码路径已就绪，未实测）。

## 后续

- 安装 pgvector 后执行迁移 29，再在 `store.py` 增加 `embedding_vec` 写入与 `<=>` 查询即可切换；
- 或者换支持 embeddings 的供应商（OpenAI / 智谱 / 通义）。
