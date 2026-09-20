-- ============================================================================
-- Day 16 教学探针：ON CONFLICT ... DO NOTHING 到底依赖什么
--
-- 全程 BEGIN / ROLLBACK，跑完库零痕迹（复核见文件末尾两条 SELECT）。
-- 只回答两个问题：
--   A. 约束在位时，「同一明细插两次」各自的影响行数是多少？
--   B. 把唯一约束摘掉后，同一句 SQL 会「悄悄变弱」还是「直接报错」？
--
-- 用法（PowerShell）：
--   Get-Content -Raw -Encoding utf8 backend/loadtest/day16-onconflict-demo.sql |
--     & $docker exec -i -e PGCLIENTENCODING=UTF8 mallx-postgres psql -U mallx -d mallx
-- ⚠️ 输出里的标签一律用英文：PGCLIENTENCODING 管不到 psql 自身的回显。
-- ============================================================================


-- ======================= 对照 A：约束在位 =======================
BEGIN;

INSERT INTO reviews (user_id, product_id, order_id, order_item_id,
                     rating, content, status, created_at, updated_at)
VALUES (1, 1, 1, 999001, 5, 'first', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT (order_item_id) DO NOTHING;

INSERT INTO reviews (user_id, product_id, order_id, order_item_id,
                     rating, content, status, created_at, updated_at)
VALUES (1, 1, 1, 999001, 1, 'second', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT (order_item_id) DO NOTHING;

SELECT 'A: rows for order_item_id=999001 after two inserts' AS label, count(*) AS n
  FROM reviews
 WHERE order_item_id = 999001;

ROLLBACK;


-- ============ 实验 B：摘掉唯一约束，同一句 SQL 的命运 ============
-- 预期：不是「防线变弱」，而是语句【直接报错】——
--       PG 要求 ON CONFLICT 的推断目标必须有一个匹配的唯一索引/约束。
BEGIN;

ALTER TABLE reviews DROP CONSTRAINT uk_reviews_order_item;

INSERT INTO reviews (user_id, product_id, order_id, order_item_id,
                     rating, content, status, created_at, updated_at)
VALUES (1, 1, 1, 999002, 5, 'no-constraint', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT (order_item_id) DO NOTHING;

SELECT 'B: this line is skipped once the block is aborted' AS label;

ROLLBACK;


-- ======================= 复核：零痕迹 =======================
SELECT 'verify: uk_reviews_order_item still exists' AS label, count(*) AS n
  FROM pg_constraint
 WHERE conname = 'uk_reviews_order_item';

SELECT 'verify: reviews total rows' AS label, count(*) AS n
  FROM reviews;

SELECT 'verify: leftover demo rows (must be 0)' AS label, count(*) AS n
  FROM reviews
 WHERE order_item_id IN (999001, 999002);
