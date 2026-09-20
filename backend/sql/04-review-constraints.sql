-- ============================================================
-- MallX 数据库补丁 04：评价表约束（Day 16）
-- 数据库：mallx（PostgreSQL 16）
--
-- 补齐 reviews 表的两处缺口（Day 03 建表时留的）：
--   ① order_item_id 可空   → SET NOT NULL
--   ② 无唯一约束           → UNIQUE (order_item_id)
--
-- ★★ 两条缺一不可：PostgreSQL 的 UNIQUE 约束【豁免 NULL】——
--    列可空时两行 NULL 互不相等、全都合法，约束形同虚设；
--    更坑的是 INSERT ... ON CONFLICT DO NOTHING 也会被 NULL 行整条绕过。
--    （实测见 backend/loadtest/day16-probe.sql 的 PROBE 3 / 5）
-- ★ 顺序：先 SET NOT NULL（体检存量数据）再 ADD CONSTRAINT（上锁）。
--
-- 该脚本可重复执行（幂等），可直接在 mallx 库中运行
-- 执行前请确保已连接 mallx 库：\c mallx
-- ============================================================

DO $$
BEGIN
    -- ① 体检 + 上锁：还有 NULL 就是脏数据，SET NOT NULL 会当场报错（这正是我们要的）
    IF EXISTS (SELECT 1
                 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name   = 'reviews'
                  AND column_name  = 'order_item_id'
                  AND is_nullable  = 'YES') THEN
        ALTER TABLE reviews ALTER COLUMN order_item_id SET NOT NULL;
        RAISE NOTICE '[04] reviews.order_item_id -> NOT NULL';
    ELSE
        RAISE NOTICE '[04] reviews.order_item_id already NOT NULL, skipped';
    END IF;

    -- ② 一明细一评：唯一约束是「重复评价」防线的最终依据
    IF NOT EXISTS (SELECT 1
                     FROM pg_constraint
                    WHERE conrelid = 'reviews'::regclass
                      AND conname  = 'uk_reviews_order_item') THEN
        ALTER TABLE reviews ADD CONSTRAINT uk_reviews_order_item UNIQUE (order_item_id);
        RAISE NOTICE '[04] uk_reviews_order_item created';
    ELSE
        RAISE NOTICE '[04] uk_reviews_order_item already exists, skipped';
    END IF;
END $$;
