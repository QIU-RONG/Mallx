-- ============================================================================
-- Day 13 Step 3 · 收工：拆掉审计触发器
-- 顺序与 setup 相反：先触发器、后函数、最后表。
-- ============================================================================

DROP TRIGGER IF EXISTS trg_pay13_stock_audit ON inventories;
DROP FUNCTION IF EXISTS fn_pay13_stock_audit();
DROP TABLE    IF EXISTS pay13_stock_audit;

SELECT 'audit removed' AS status;
