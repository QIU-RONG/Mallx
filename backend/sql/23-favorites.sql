-- ============================================================
-- 商品收藏（Day 82）
-- 一人一商品一行；不软删（取消收藏直接物理删）。
-- ============================================================

CREATE TABLE IF NOT EXISTS user_favorites (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT    NOT NULL,
    product_id BIGINT    NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uk_favorites_user_product') THEN
        ALTER TABLE user_favorites ADD CONSTRAINT uk_favorites_user_product UNIQUE (user_id, product_id);
        RAISE NOTICE '[23] uk_favorites_user_product created';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_favorites_user_time ON user_favorites (user_id, created_at DESC);

SELECT count(*) AS favorites FROM user_favorites;
