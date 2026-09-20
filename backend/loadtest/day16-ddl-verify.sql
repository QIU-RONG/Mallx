-- ============================================================
-- Day 16：04 补丁执行后的「牙齿」复核
-- 用法：Get-Content -Raw day16-ddl-verify.sql | docker exec -i -e PGCLIENTENCODING=UTF8 mallx-postgres psql -U mallx -d mallx
-- ★ 对施工前探针（day16-probe.sql）的对照：
--   探针 1「同一明细插两次都成功」 → 这里必须变成 23505
--   探针 3「两行 NULL 都成功」     → 这里必须变成 23502
--   探针 4「ON CONFLICT 返回 0 行」 → 这里必须复现
-- ★ 全程 BEGIN/ROLLBACK，跑完库零痕迹
-- ============================================================

\echo ''
\echo '### TEETH 1: duplicate order_item_id must now FAIL with 23505 ###'
BEGIN;
INSERT INTO reviews (user_id, product_id, order_id, order_item_id, rating, status)
SELECT o.user_id, oi.product_id, oi.order_id, oi.id, 5, 1
  FROM order_items oi JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = (SELECT min(id) FROM order_items);
INSERT INTO reviews (user_id, product_id, order_id, order_item_id, rating, status)
SELECT o.user_id, oi.product_id, oi.order_id, oi.id, 4, 1
  FROM order_items oi JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = (SELECT min(id) FROM order_items);
ROLLBACK;

\echo ''
\echo '### TEETH 2: ON CONFLICT DO NOTHING -> 1st INSERT 0 1, 2nd INSERT 0 0 ###'
BEGIN;
INSERT INTO reviews (user_id, product_id, order_id, order_item_id, rating, status)
SELECT o.user_id, oi.product_id, oi.order_id, oi.id, 5, 1
  FROM order_items oi JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = (SELECT min(id) FROM order_items)
ON CONFLICT (order_item_id) DO NOTHING;
INSERT INTO reviews (user_id, product_id, order_id, order_item_id, rating, status)
SELECT o.user_id, oi.product_id, oi.order_id, oi.id, 4, 1
  FROM order_items oi JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = (SELECT min(id) FROM order_items)
ON CONFLICT (order_item_id) DO NOTHING;
SELECT count(*) AS rows_after_two_attempts FROM reviews;
ROLLBACK;

\echo ''
\echo '### TEETH 3: NULL order_item_id must now FAIL with 23502 ###'
BEGIN;
INSERT INTO reviews (user_id, product_id, order_id, order_item_id, rating, status)
SELECT o.user_id, oi.product_id, oi.order_id, NULL, 5, 1
  FROM order_items oi JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = (SELECT min(id) FROM order_items);
ROLLBACK;

\echo ''
\echo '### FINAL: reviews must still be EMPTY ###'
SELECT count(*) AS reviews_rows FROM reviews;
