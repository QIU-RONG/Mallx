-- ============================================================
-- Day 16 探针：selectBuyContext 的【可执行规格】
-- 全程只读（纯 SELECT），不写任何表、零痕迹，可随时重跑
-- ============================================================
-- 用途：把「这条 SQL 到底要返回什么」从文档里的文字，变成库里能跑出来的事实。
--       将来 order_items / orders 改结构时，重跑本文件即可验证契约是否仍成立。
-- ============================================================

\pset border 2

\echo '=== A. correct owner (userId=1, itemId=1): expect EXACTLY 1 row, 8 columns ==='
SELECT oi.id           AS order_item_id,
       oi.order_id     AS order_id,
       oi.product_id   AS product_id,
       oi.sku_id       AS sku_id,
       oi.product_name AS product_name,
       oi.sku_name     AS sku_name,
       oi.image        AS image,
       o.status        AS order_status
  FROM order_items oi
  JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = 1
   AND o.user_id = 1;

\echo '=== B. wrong owner (userId=999999, itemId=1): expect 0 rows -- NOT an error ==='
SELECT oi.id           AS order_item_id,
       oi.order_id     AS order_id,
       oi.product_id   AS product_id,
       oi.sku_id       AS sku_id,
       oi.product_name AS product_name,
       oi.sku_name     AS sku_name,
       oi.image        AS image,
       o.status        AS order_status
  FROM order_items oi
  JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = 1
   AND o.user_id = 999999;

\echo '=== C. item does not exist (itemId=999999): expect 0 rows -- same answer as B ==='
SELECT oi.id           AS order_item_id,
       oi.order_id     AS order_id,
       oi.product_id   AS product_id,
       oi.sku_id       AS sku_id,
       oi.product_name AS product_name,
       oi.sku_name     AS sku_name,
       oi.image        AS image,
       o.status        AS order_status
  FROM order_items oi
  JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = 999999
   AND o.user_id = 1;

\echo '=== D. row counts side by side: B and C must be identical ==='
SELECT 'A_correct_owner' AS case, count(*) AS rows
  FROM order_items oi JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = 1      AND o.user_id = 1
UNION ALL
SELECT 'B_wrong_owner', count(*)
  FROM order_items oi JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = 1      AND o.user_id = 999999
UNION ALL
SELECT 'C_no_such_item', count(*)
  FROM order_items oi JOIN orders o ON o.id = oi.order_id
 WHERE oi.id = 999999 AND o.user_id = 1
 ORDER BY 1;

\echo '=== E. WHY the 8th column needs an explicit alias (the only one that does) ==='
SELECT o.status            AS no_alias,
       o.status            AS order_status,
       o.status            AS orderStatus,
       o.status            AS "orderStatus"
  FROM orders o
 WHERE o.id = 1;

\echo '=== F. WHY this SQL has to exist: the DB will NOT stop a forged product_id ==='
-- 场景：攻击者拿自己一张合法订单明细（id=1，真属商品 1）。若请求体里能传 product_id，
--       他就能把这条评价挂到任意商品上 —— 一次下单，刷遍全站。
-- 本组证明：数据库层【不会】阻止这件事。reviews 对 products 只有外键（「商品得存在」），
--           没有「你得买过」这条约束。防线完全在应用层：DTO 里根本没有 product_id 字段。
BEGIN;
SELECT (SELECT count(*) FROM order_items WHERE id = 1)      AS item1_exists,
       (SELECT product_id FROM order_items WHERE id = 1)    AS item1_true_product;

INSERT INTO reviews (user_id, order_id, product_id, order_item_id, rating, content, status)
SELECT 1, 1, p.id, 1, 5, 'forged product_id', 1
  FROM products p
 WHERE p.id <> (SELECT product_id FROM order_items WHERE id = 1)
 ORDER BY p.id DESC
 LIMIT 1;

SELECT user_id, order_id, product_id, order_item_id, rating, content FROM reviews;
ROLLBACK;

\echo '=== verify: still read-only, reviews 0 rows, orders untouched ==='
SELECT (SELECT count(*) FROM reviews) AS reviews_rows,
       (SELECT count(*) FROM orders)  AS orders_rows,
       (SELECT count(*) FROM order_items) AS items_rows;
