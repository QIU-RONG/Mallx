-- ============================================================
-- Day 14 开工前基线校准：把「实验遗留」的库存按业务守恒归位
--
-- 依据：
--   locked 应 == SUM(PENDING_PAYMENT 订单的 order_items.quantity)
--   sold   应 == SUM(PAID            订单的 order_items.quantity)
--
-- 口径（Day-14 文档 §0.3）：
--   多出的（drift > 0）→ 退回 available   （有依据：本就不该被占/被卖）
--   缺少的（drift < 0）→ 【不自动补】     （补 = 凭空造货，必须人工查）
--
-- ⚠️ 第 3 段「locked 全归零」【只对「无待支付订单」成立】。
--    若存在待支付订单，必须改成「只退多出的部分」，否则会把在途订单的锁一起退掉。
-- ============================================================

\pset border 2

\echo '=== BEFORE ==='
SELECT sku_id, total_stock, available_stock, locked_stock, sold_stock,
       (available_stock + locked_stock + sold_stock = total_stock) AS identity_ok
FROM inventories ORDER BY sku_id;

\echo '=== BEFORE drift (business conservation) ==='
SELECT i.sku_id,
       i.locked_stock AS actual_locked, COALESCE(l.want, 0) AS want_locked,
       i.locked_stock - COALESCE(l.want, 0) AS drift_locked,
       i.sold_stock   AS actual_sold,   COALESCE(s.want, 0) AS want_sold,
       i.sold_stock   - COALESCE(s.want, 0) AS drift_sold
FROM inventories i
LEFT JOIN (SELECT oi.sku_id, sum(oi.quantity) AS want
           FROM order_items oi JOIN orders o ON o.id = oi.order_id
           WHERE o.status = 'PENDING_PAYMENT' GROUP BY oi.sku_id) l ON l.sku_id = i.sku_id
LEFT JOIN (SELECT oi.sku_id, sum(oi.quantity) AS want
           FROM order_items oi JOIN orders o ON o.id = oi.order_id
           WHERE o.status = 'PAID' GROUP BY oi.sku_id) s ON s.sku_id = i.sku_id
WHERE i.locked_stock <> COALESCE(l.want, 0) OR i.sold_stock <> COALESCE(s.want, 0)
ORDER BY i.sku_id;

BEGIN;

-- 1) sold 归位 A：有 PAID 明细的 SKU，多出的退回 available
WITH want_sold AS (
    SELECT oi.sku_id, sum(oi.quantity) AS want
    FROM order_items oi JOIN orders o ON o.id = oi.order_id
    WHERE o.status = 'PAID' GROUP BY oi.sku_id
)
UPDATE inventories i
SET available_stock = i.available_stock + (i.sold_stock - w.want),
    sold_stock      = w.want,
    updated_at      = CURRENT_TIMESTAMP
FROM want_sold w
WHERE w.sku_id = i.sku_id
  AND i.sold_stock > w.want;

-- 1b) sold 归位 B：完全没有 PAID 明细的 SKU（LEFT JOIN 落空的那种），sold 全退
UPDATE inventories i
SET available_stock = i.available_stock + i.sold_stock,
    sold_stock      = 0,
    updated_at      = CURRENT_TIMESTAMP
WHERE i.sold_stock > 0
  AND NOT EXISTS (
      SELECT 1 FROM order_items oi JOIN orders o ON o.id = oi.order_id
      WHERE oi.sku_id = i.sku_id AND o.status = 'PAID');

-- 2) locked 归位：无待支付订单时，locked 全属「无主锁定」→ 退回 available
UPDATE inventories i
SET available_stock = i.available_stock + i.locked_stock,
    locked_stock    = 0,
    updated_at      = CURRENT_TIMESTAMP
WHERE i.locked_stock > 0
  AND NOT EXISTS (SELECT 1 FROM orders WHERE status = 'PENDING_PAYMENT');

COMMIT;

\echo '=== AFTER ==='
SELECT sku_id, total_stock, available_stock, locked_stock, sold_stock,
       (available_stock + locked_stock + sold_stock = total_stock) AS identity_ok
FROM inventories ORDER BY sku_id;

\echo '=== AFTER drift (must be 0 rows) ==='
SELECT i.sku_id,
       i.locked_stock - COALESCE(l.want, 0) AS drift_locked,
       i.sold_stock   - COALESCE(s.want, 0) AS drift_sold
FROM inventories i
LEFT JOIN (SELECT oi.sku_id, sum(oi.quantity) AS want
           FROM order_items oi JOIN orders o ON o.id = oi.order_id
           WHERE o.status = 'PENDING_PAYMENT' GROUP BY oi.sku_id) l ON l.sku_id = i.sku_id
LEFT JOIN (SELECT oi.sku_id, sum(oi.quantity) AS want
           FROM order_items oi JOIN orders o ON o.id = oi.order_id
           WHERE o.status = 'PAID' GROUP BY oi.sku_id) s ON s.sku_id = i.sku_id
WHERE i.locked_stock <> COALESCE(l.want, 0) OR i.sold_stock <> COALESCE(s.want, 0)
ORDER BY i.sku_id;

\echo '=== orders / payments (unchanged, only inventories touched) ==='
SELECT status, count(*) AS cnt FROM orders GROUP BY status ORDER BY status;
SELECT count(*) AS payments_rows FROM payments;
