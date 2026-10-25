-- ============================================================
-- 评价晒图（Day 80）
-- reviews.images 列是 jsonb，但 MyBatis 自定义 TypeHandler 只对写入生效、
-- 读取时要额外 resultMap —— 与其在 review 域再维护一套 JSONB 映射，
-- 不如把「一张图一行」建表：查询简单、可排序、可逐张删。
-- ============================================================

CREATE TABLE IF NOT EXISTS review_images (
    id         BIGSERIAL PRIMARY KEY,
    review_id  BIGINT       NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    image_url  VARCHAR(500) NOT NULL,
    sort       INT          NOT NULL DEFAULT 0,
    created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_review_images_review ON review_images (review_id);

SELECT count(*) AS review_images FROM review_images;
