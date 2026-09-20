-- ============================================================
-- Day 16 开工前探针：证明 reviews 表的三处缺口 + DDL 该怎么加
-- 用法：Get-Content -Raw day16-probe.sql | docker exec -i -e PGCLIENTENCODING=UTF8 mallx-postgres psql -U mallx -d mallx
-- ★ 所有段落在 BEGIN/ROLLBACK 内 —— 跑完库回到原样（id 序列会前进，属正常）
-- ★ 刻意不写 ON_ERROR_STOP：预期会失败的语句正是证据
-- ★ 标签一律英文：PGCLIENTENCODING 管不到 psql 的 \echo（中文会显示成 ?）
-- ============================================================

\echo ''
\echo '### PROBE 0: reviews columns (is_nullable? default?) ###'
SELECT column_name, data_type, is_nullable, column_default
  FROM information_schema.columns
 WHERE table_name = 'reviews'
 ORDER BY ordinal_position;

\echo ''
\echo '### PROBE 0b: existing constraints on reviews (is there any UNIQUE?) ###'
SELECT conname, contype, pg_get_constraintdef(oid) AS def
  FROM pg_constraint
 WHERE conrelid = 'reviews'::regclass
 ORDER BY contype, conname;

\echo ''
\echo '### PROBE 1: WITHOUT unique constraint -> same order_item_id inserted TWICE, both succeed (gap is REAL) ###'
BEGIN;
INSERT INTO reviews (user_id, product_id, order_id, order_item_id, rating, content, status)
SELECT o.user_id, oi.product_id, oi.order_id, oi.id, 5, 'probe-A', 1
  FROM order_items oi JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = (SELECT min(id) FROM order_items);
INSERT INTO reviews (user_id, product_id, order_id, order_item_id, rating, content, status)
SELECT o.user_id, oi.product_id, oi.order_id, oi.id, 4, 'probe-B', 1
  FROM order_items oi JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = (SELECT min(id) FROM order_items);
SELECT count(*) AS rows_for_same_item FROM reviews;
ROLLBACK;

\echo ''
\echo '### PROBE 2: WITH UNIQUE(order_item_id) -> second INSERT must fail 23505 ###'
BEGIN;
ALTER TABLE reviews ADD CONSTRAINT uk_reviews_order_item UNIQUE (order_item_id);
INSERT INTO reviews (user_id, product_id, order_id, order_item_id, rating, content, status)
SELECT o.user_id, oi.product_id, oi.order_id, oi.id, 5, 'probe-A2', 1
  FROM order_items oi JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = (SELECT min(id) FROM order_items);
INSERT INTO reviews (user_id, product_id, order_id, order_item_id, rating, content, status)
SELECT o.user_id, oi.product_id, oi.order_id, oi.id, 4, 'probe-B2', 1
  FROM order_items oi JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = (SELECT min(id) FROM order_items);
ROLLBACK;

\echo ''
\echo '### PROBE 3: NULL order_item_id is EXEMPT from UNIQUE -> two NULL rows BOTH succeed ###'
BEGIN;
ALTER TABLE reviews ADD CONSTRAINT uk_reviews_order_item UNIQUE (order_item_id);
INSERT INTO reviews (user_id, product_id, order_id, order_item_id, rating, content, status)
SELECT o.user_id, oi.product_id, oi.order_id, NULL, 5, 'probe-null-1', 1
  FROM order_items oi JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = (SELECT min(id) FROM order_items);
INSERT INTO reviews (user_id, product_id, order_id, order_item_id, rating, content, status)
SELECT o.user_id, oi.product_id, oi.order_id, NULL, 3, 'probe-null-2', 1
  FROM order_items oi JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = (SELECT min(id) FROM order_items);
SELECT count(*) AS rows_with_null_item FROM reviews;
ROLLBACK;

\echo ''
\echo '### PROBE 4: ON CONFLICT (order_item_id) DO NOTHING -> 2nd attempt returns INSERT 0 0 (CAS semantics) ###'
BEGIN;
ALTER TABLE reviews ALTER COLUMN order_item_id SET NOT NULL;
ALTER TABLE reviews ADD CONSTRAINT uk_reviews_order_item UNIQUE (order_item_id);
INSERT INTO reviews (user_id, product_id, order_id, order_item_id, rating, content, status)
SELECT o.user_id, oi.product_id, oi.order_id, oi.id, 5, 'probe-oc-1', 1
  FROM order_items oi JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = (SELECT min(id) FROM order_items)
ON CONFLICT (order_item_id) DO NOTHING;
INSERT INTO reviews (user_id, product_id, order_id, order_item_id, rating, content, status)
SELECT o.user_id, oi.product_id, oi.order_id, oi.id, 4, 'probe-oc-2', 1
  FROM order_items oi JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = (SELECT min(id) FROM order_items)
ON CONFLICT (order_item_id) DO NOTHING;
SELECT count(*) AS rows_after_two_attempts FROM reviews;
ROLLBACK;

\echo ''
\echo '### PROBE 5: UNIQUE only, WITHOUT NOT NULL -> NULL rows silently BYPASS the guard ###'
BEGIN;
ALTER TABLE reviews ADD CONSTRAINT uk_reviews_order_item UNIQUE (order_item_id);
INSERT INTO reviews (user_id, product_id, order_id, order_item_id, rating, content, status)
SELECT o.user_id, oi.product_id, oi.order_id, NULL, 5, 'probe-null-x', 1
  FROM order_items oi JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = (SELECT min(id) FROM order_items)
ON CONFLICT (order_item_id) DO NOTHING;
INSERT INTO reviews (user_id, product_id, order_id, order_item_id, rating, content, status)
SELECT o.user_id, oi.product_id, oi.order_id, NULL, 4, 'probe-null-y', 1
  FROM order_items oi JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = (SELECT min(id) FROM order_items)
ON CONFLICT (order_item_id) DO NOTHING;
SELECT count(*) AS rows_with_null_after_two_attempts FROM reviews;
ROLLBACK;

\echo ''
\echo '### PROBE 6: WITH NOT NULL -> NULL order_item_id is rejected 23502 ###'
BEGIN;
ALTER TABLE reviews ALTER COLUMN order_item_id SET NOT NULL;
INSERT INTO reviews (user_id, product_id, order_id, order_item_id, rating, status)
SELECT o.user_id, oi.product_id, oi.order_id, NULL, 5, 1
  FROM order_items oi JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = (SELECT min(id) FROM order_items);
ROLLBACK;

\echo ''
\echo '### PROBE 7: after ROLLBACK -> reviews EMPTY, no new constraint, column still nullable ###'
SELECT count(*) AS reviews_rows_after_rollback FROM reviews;
SELECT count(*) AS uk_constraint_after_rollback FROM pg_constraint
 WHERE conrelid = 'reviews'::regclass AND conname = 'uk_reviews_order_item';
SELECT is_nullable AS order_item_id_nullable_now FROM information_schema.columns
 WHERE table_name = 'reviews' AND column_name = 'order_item_id';
