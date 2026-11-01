-- 28 AI 运营指标（Day 116）：耗时与拒答落库
ALTER TABLE ai_messages ADD COLUMN IF NOT EXISTS elapsed_ms INT;
ALTER TABLE ai_messages ADD COLUMN IF NOT EXISTS refusal BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_ai_messages_created ON ai_messages (created_at);
SELECT count(*) AS ai_messages FROM ai_messages;
