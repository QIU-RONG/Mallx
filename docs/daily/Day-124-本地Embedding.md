# Day 124 · 本地 Embedding（BAAI/bge-small-zh-v1.5）

用户选择「本地模型」方案：不依赖 embeddings 供应商 key。

## 实现

- astembed==0.7.4 + BAAI/bge-small-zh-v1.5（512 维，CPU 可跑；模型首次下载经 HF 镜像）；
- embed.py 增加 EMBEDDING_MODE=local：
  - local → fastembed；失败自动回退 hash；
  - hash → 强制离线；
  - auto → 有 key 用远程，否则 hash；
- kb_lib/embed.py 自己加载 .env，保证 kb_ingest.py / 评测脚本与线上服务同一套配置；
- fastembed 返回 numpy.float32，已转 float（否则 psycopg2 报 can't adapt type 'numpy.float32'）；
- pgvector 可选迁移的维度同步改成 ector(512)。

## 效果（本地模型 vs 哈希向量）

| 指标 | hash | 本地 bge-small-zh |
|---|---|---|
| hit@1 | 43/50 | **46/50** |
| hit@4 | 49/50 | **50/50** |

之前漏掉的「包邮门槛是多少」现在能正确命中运费规则。

## 线上验证

- /health：configured=true, embeddingMode=local；
- 真实模型 + 本地向量：「满多少免运费」「包邮门槛是多少」都返回 grounded + 引用来源；
- 默认仍是 real[] 存向量 + Python 余弦（pgvector 扩展仍缺，环境限制未变）。
