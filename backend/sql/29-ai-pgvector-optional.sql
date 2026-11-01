-- 29 可选：pgvector（Day 122）
-- 本机 PostgreSQL 未安装 vector 扩展时，脚本会跳过并给出 NOTICE，
-- Python 侧继续使用 real[] + 余弦（store.py 自动降级）。
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') THEN
        CREATE EXTENSION IF NOT EXISTS vector;
        ALTER TABLE ai_kb_chunks ADD COLUMN IF NOT EXISTS embedding_vec vector(512);
        CREATE INDEX IF NOT EXISTS idx_ai_kb_vec ON ai_kb_chunks
            USING ivfflat (embedding_vec vector_cosine_ops) WITH (lists = 10);
        RAISE NOTICE '[29] pgvector enabled';
    ELSE
        RAISE NOTICE '[29] pgvector 不可用，跳过（继续 real[] + Python 余弦）';
    END IF;
END $$;
SELECT count(*) AS ai_kb_chunks FROM ai_kb_chunks;
