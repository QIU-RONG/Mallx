-- ============================================================
-- MallX DDL 补丁（Day 21）—— orders 增加 discount_amount（优惠额快照）
-- 说明：需在 01-schema / 02-index / 03-data 之后执行。幂等，可重复执行。
-- ============================================================
--
-- ★ 为什么需要它（Day 21 = 优惠券阶段二：下单抵扣 + 核销）：
--   Day 20 只做了「券的产生与获取」；阶段二在下单时算抵扣，于是订单需要记住
--   「这一单到底优惠了多少钱」。而 orders 建表时【只有】两个金额列：
--
--       total_amount   商品总额（Σ price × quantity）
--       pay_amount     实付金额
--
--   三个量里知道两个，理论上能反推出第三个：discount = total - pay。
--   但「能反推」不等于「该反推」，漏掉一列有两个代价：
--     ① 分不清「没用券」与「用了 0 元券」—— 两者都是 pay == total；
--     ② 订单详情/退款/对账都要自己再算一遍，规则一变口径就漂。
--   ⇒ 存一份快照：「下单那一刻优惠了多少」是一个【历史事实】，
--      不该被后来改动的券规则、或者读的人各自的理解影响。
--
-- ★★ 为什么是 DEFAULT 0 而不是可空：
--   历史订单（Day 12 至今）都没用券 → 它们的 discount_amount 就是 0，不是「未知」。
--   NOT NULL DEFAULT 0 让存量行【天然正确】，不需要任何 UPDATE 回填。
--
--   ★ 对照 Day 20 的 user_coupons 加 UNIQUE：那次目标列是可空的，
--     必须先 SET NOT NULL 再加 UNIQUE（PG 的 UNIQUE 豁免 NULL，会错得安静）。
--     本次新列直接带 NOT NULL DEFAULT，一步到位 —— 但前提仍然要查（见 1.1）。
--
-- ★ 本补丁【不写】回填 UPDATE：
--   存量行的 pay_amount 本就等于 total_amount（Day 12 的注释写着「V1.0 无优惠」），
--   所以 discount_amount = 0 已与之一致。★ 下面 3.3 段就是这条一致性的实证，
--   而不是「我觉得应该一致」。
-- ============================================================


-- ------------------------------------------------------------
-- 一、前提体检（★ 必须先看这两段输出）
-- ------------------------------------------------------------

-- 1.1 列是否已经存在：★ 期望 0 行。
--     若返回 1 行 → 说明本补丁跑过了，直接跳到第三节自检。
SELECT column_name, data_type, is_nullable, column_default
  FROM information_schema.columns
 WHERE table_name = 'orders'
   AND column_name = 'discount_amount';

-- 1.2 存量一致性体检：★ 期望 0 行。
--     返回的行 = 「实付 ≠ 总额」的历史订单。正常情况下一行都没有；
--     若真有，那说明在加这一列之前就存在金额不一致的订单 ——
--     ⚠️ 那是另一件事，【先别急着加列】，把清单给人看一眼再决定。
SELECT id, order_no, total_amount, pay_amount
  FROM orders
 WHERE pay_amount <> total_amount
 ORDER BY id;


-- ------------------------------------------------------------
-- 二、加列（幂等）
-- ------------------------------------------------------------
-- 用 DO 块 + information_schema 判断，重复执行不会报 "column already exists"。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'orders' AND column_name = 'discount_amount'
    ) THEN
        ALTER TABLE orders
          ADD COLUMN discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0;
    END IF;
END $$;

-- ★ 精度与 total_amount / pay_amount 保持一致（都是 NUMERIC(12,2)）——
--   三列要一起参与减法，精度类型不一致时 PG 会做隐式提升，结果虽然对，
--   但「为什么这一列是 12,2 那一列是别的」会在对账时变成一个没人回答得出的问题。


-- ------------------------------------------------------------
-- 三、自检（执行后请人工核对这四段输出）
-- ------------------------------------------------------------

-- 3.1 列在不在：★ 期望 1 行，is_nullable = NO，column_default = 0
SELECT column_name, data_type, numeric_precision, numeric_scale,
       is_nullable, column_default
  FROM information_schema.columns
 WHERE table_name = 'orders'
   AND column_name = 'discount_amount';

-- 3.2 存量行是否全部为 0：★ 期望 nonzero_rows = 0
SELECT count(*)                                  AS total_rows,
       count(*) FILTER (WHERE discount_amount = 0)  AS zero_rows,
       count(*) FILTER (WHERE discount_amount <> 0) AS nonzero_rows
  FROM orders;

-- 3.3 ★★ 金额恒等式的实证（不是「我觉得应该一致」）：
--     pay_amount = total_amount - discount_amount   ★ 期望 0
--     ★ 这条断言在阶段二写完【之后仍然要成立】—— 直接复用它验收新订单，
--       比另写一条「新订单 discount 正确」更省事，而且它管的是【整张表】。
SELECT count(*) AS inconsistent
  FROM orders
 WHERE pay_amount <> total_amount - discount_amount;

-- 3.4 功能验证（零痕迹：包在事务里，最后 ROLLBACK）
--     证明这一列【可写】且 NOT NULL 不拦合法值 —— 光看元数据只能证明列存在。
--     ⚠️ 若 orders 是空表，UPDATE 影响 0 行，下面的 SELECT 也返回 0 行：
--        那说明本段没验到东西（不是通过）。此时先造一单再来。
BEGIN;
    UPDATE orders
       SET discount_amount = 12.34
     WHERE id = (SELECT min(id) FROM orders);

    SELECT id, total_amount, pay_amount, discount_amount,
           (pay_amount = total_amount - discount_amount) AS still_consistent
      FROM orders
     WHERE id = (SELECT min(id) FROM orders);
ROLLBACK;
-- ★ 判据：读出来的 discount_amount 是 12.34（说明可写），
--   still_consistent = f（因为只改了 discount 没改 pay，恒等式被人为破坏）——
--   这正是「3.3 那条全表断言有意义」的反向证明。
