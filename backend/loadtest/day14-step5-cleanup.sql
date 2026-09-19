-- ============================================================================
-- Day 14 · 第 5 步收官清理：把测试产物全部倒回去
-- ----------------------------------------------------------------------------
-- 要清掉的东西（全部由本次 Day 14 的验收实验产生）：
--   orders      #9016 ~ #9024   9 张（4 PAID + 5 CANCELLED）
--   payments    9 行（对应 4 张 PAID 单）
--   order_items 9 行
--   inventory_logs 18 行（本次第 4 步实验的全部流水）
--   inventories sku4  143/0/7  →  150/147/0/3（§0.3 基线）
--   （sku2 早前已被正常取消归位 80/0/0，无需处理）
--
-- ★★ 为什么流水也要一起删 —— 这是本次清理唯一需要讲清楚的判断：
--    流水记录的是「库存发生过什么」。既然现在要把库存**倒回**基线，
--    账本就必须跟着倒；否则账本说「末值 143」而表里是 147，
--    day14-reconcile.py 的审计会直接报 DRIFT —— 那就是账本在说谎。
--    「只倒库存、不倒账本」= 制造一次假漂移，比不清理更糟。
--    （证据已完整保留在 day14-ledger-verify-report.txt 与
--      day14-reconcile-report.txt 里，不依赖库内数据。）
--
-- ★ available 不硬编码：写成 total_stock - locked - sold，
--   这样恒等式 total = available + locked + sold 由构造保证。
--
-- ★ 删订单必须按外键顺序：payments / order_items 都引用 orders。
--   inventory_logs.reference_id 没有外键，所以它不拦删除，但也因此
--   必须手工清理（数据库不会帮你级联）。
--
-- 用法：docker exec -i mallx-postgres psql -U mallx -d mallx < 本文件
-- ============================================================================

\pset border 2

\echo '=== BEFORE: 将被删除的订单 ==='
SELECT o.id, o.status,
       (o.paid_at IS NOT NULL)      AS paid,
       (o.cancelled_at IS NOT NULL) AS cancelled,
       (SELECT count(*) FROM payments p WHERE p.order_id = o.id) AS pay_rows
FROM orders o WHERE o.id BETWEEN 9016 AND 9024 ORDER BY o.id;

\echo '=== BEFORE: sku4 / sku2 ==='
SELECT sku_id, total_stock, available_stock, locked_stock, sold_stock
FROM inventories WHERE sku_id IN (2, 4) ORDER BY sku_id;

\echo '=== BEFORE: 流水行数（按 sku） ==='
SELECT sku_id, count(*) FROM inventory_logs GROUP BY sku_id ORDER BY sku_id;

BEGIN;

-- ① 外键顺序：先子表，后主表
DELETE FROM payments    WHERE order_id BETWEEN 9016 AND 9024;
DELETE FROM order_items WHERE order_id BETWEEN 9016 AND 9024;
DELETE FROM orders      WHERE id       BETWEEN 9016 AND 9024;

-- ② 账本一起倒（理由见文件头）
DELETE FROM inventory_logs;

-- ③ sku4 归位：available 由恒等式推出，不硬编码
UPDATE inventories
   SET locked_stock    = 0,
       sold_stock      = 3,
       available_stock = total_stock - 3,
       updated_at      = CURRENT_TIMESTAMP
 WHERE sku_id = 4;

COMMIT;

\echo '=== AFTER: 订单按状态分布（应只剩历史单） ==='
SELECT status, count(*) AS cnt FROM orders GROUP BY status ORDER BY status;

\echo '=== AFTER: orders / payments / order_items / inventory_logs 行数 ==='
SELECT (SELECT count(*) FROM orders)         AS orders,
       (SELECT count(*) FROM payments)       AS payments,
       (SELECT count(*) FROM order_items)    AS order_items,
       (SELECT count(*) FROM inventory_logs) AS inventory_logs;

\echo '=== AFTER: 7 个 SKU 必须逐字段等于 §0.3 基线 ==='
SELECT sku_id, total_stock, available_stock, locked_stock, sold_stock,
       (total_stock = available_stock + locked_stock + sold_stock) AS identity_ok
FROM inventories ORDER BY sku_id;

\echo '=== AFTER: 业务守恒（drift 必须 0 行） ==='
SELECT i.sku_id,
       i.locked_stock - COALESCE(l.want, 0) AS drift_locked,
       i.sold_stock   - COALESCE(s.want, 0) AS drift_sold
FROM inventories i
LEFT JOIN (SELECT oi.sku_id, sum(oi.quantity) AS want FROM order_items oi
           JOIN orders o ON o.id = oi.order_id
           WHERE o.status = 'PENDING_PAYMENT' GROUP BY oi.sku_id) l ON l.sku_id = i.sku_id
LEFT JOIN (SELECT oi.sku_id, sum(oi.quantity) AS want FROM order_items oi
           JOIN orders o ON o.id = oi.order_id
           WHERE o.status = 'PAID' GROUP BY oi.sku_id) s ON s.sku_id = i.sku_id
WHERE i.locked_stock <> COALESCE(l.want, 0) OR i.sold_stock <> COALESCE(s.want, 0)
ORDER BY i.sku_id;
