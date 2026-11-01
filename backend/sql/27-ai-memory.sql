-- 27 AI 会话记忆（Day 111）
CREATE TABLE IF NOT EXISTS ai_conversations (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ai_messages (
    id              BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
    role            VARCHAR(16) NOT NULL,
    content         TEXT NOT NULL,
    prompt_tokens   INT,
    completion_tokens INT,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ai_messages_conv ON ai_messages (conversation_id, id);
SELECT count(*) AS ai_conversations FROM ai_conversations;
