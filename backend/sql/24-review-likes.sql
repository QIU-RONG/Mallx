-- ============================================================
-- 评价「有用」点赞（Day 89）
-- 一人对一条评价只能点一次；取消点赞物理删除。
-- ============================================================

CREATE TABLE IF NOT EXISTS review_likes (
    id         BIGSERIAL PRIMARY KEY,
    review_id  BIGINT    NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    user_id    BIGINT    NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uk_review_likes_user') THEN
        ALTER TABLE review_likes ADD CONSTRAINT uk_review_likes_user UNIQUE (review_id, user_id);
        RAISE NOTICE '[24] uk_review_likes_user created';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_review_likes_review ON review_likes (review_id);

SELECT count(*) AS review_likes FROM review_likes;
