-- ============================================================================
-- Day 13 Step 3 · 对照组实验后的数据回滚（只针对被破坏的靶子订单）
-- ----------------------------------------------------------------------------
-- 对照组（先查后改）跑完后，靶子订单会变成：
--   payments          : +N 行（同一订单被收 N 笔钱，N = 通过检查的线程数）
--   orders.status     : PAID（本该只允许一次）
--   inventories.locked: 被扣 N 次 -> 负数
--   inventories.sold  : 被加 N 次 -> 虚高
--
-- ★★ 回滚量必须写成「N × 明细数量」，N 从 payments 的实际行数现算。
--    只按 1 次还原会【还原不足】—— 残留负数库存，而且静默不报错。
--    主组（CAS）的 N 恰好是 1，所以同一套 SQL 两种场合都对。
--
-- ★ 数量不写死，从 order_items 现算（sum(quantity)）：换靶子也不会算错。
--   available_stock 全程没被动过，所以不需要还原（这本身就是断言之一）。
--
-- 用法（target 必须显式传，写死默认值会让「换靶子」时静默算错）：
--   psql -v target=2 -f day13-restore.sql
-- ============================================================================

BEGIN;

-- ① 先数出对照组造了多少笔重复支付 —— 这就是库存被多扣的次数
--    （必须在 DELETE 之前数，删完就查不到了）
CREATE TEMP TABLE _dmg ON COMMIT DROP AS
SELECT count(*) AS times FROM payments WHERE order_id = :target;

-- ② 删掉对照组凭空造出来的支付流水
DELETE FROM payments WHERE order_id = :target;

-- ③ 订单状态退回待支付（paid_at 清空）
UPDATE orders
   SET status     = 'PENDING_PAYMENT',
       paid_at    = NULL,
       updated_at = CURRENT_TIMESTAMP
 WHERE id = :target;

-- ④ 库存逆向还原：把「多扣了 N 次的 locked」还回去，把「多记了 N 次的 sold」扣回去
UPDATE inventories i
   SET locked_stock = i.locked_stock + q.qty * (SELECT times FROM _dmg),
       sold_stock   = i.sold_stock   - q.qty * (SELECT times FROM _dmg)
  FROM (SELECT sku_id, sum(quantity) AS qty
          FROM order_items
         WHERE order_id = :target
         GROUP BY sku_id) q
 WHERE i.sku_id = q.sku_id;

COMMIT;

-- ---------------------------------------------------------------- 对账
\pset border 2
SELECT id, status, pay_amount, paid_at FROM orders WHERE id = :target;
SELECT count(*) AS payments_left FROM payments WHERE order_id = :target;
SELECT i.sku_id, i.total_stock, i.available_stock, i.locked_stock, i.sold_stock,
       (i.total_stock = i.available_stock + i.locked_stock + i.sold_stock) AS identity_ok
  FROM inventories i
 WHERE i.sku_id IN (SELECT sku_id FROM order_items WHERE order_id = :target)
 ORDER BY i.sku_id;
