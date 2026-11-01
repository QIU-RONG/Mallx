-- 26 AI 知识库（Day 109）：RAG 切片 + 向量（无 pgvector，先用 real[] 存，Python 侧算余弦）
CREATE TABLE IF NOT EXISTS ai_kb_chunks (
    id         BIGSERIAL PRIMARY KEY,
    source     VARCHAR(200) NOT NULL,
    heading    VARCHAR(200),
    content    TEXT NOT NULL,
    embedding  REAL[] NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ai_kb_source ON ai_kb_chunks (source);
SELECT count(*) AS ai_kb_chunks FROM ai_kb_chunks;
