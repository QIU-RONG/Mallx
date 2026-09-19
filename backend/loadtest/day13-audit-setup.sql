-- ============================================================================
-- Day 13 Step 3 · 库存写入审计（并发实验的证据来源）
-- ----------------------------------------------------------------------------
-- 为什么用触发器而不是 Python 轮询：一次并发支付从开始到结束只有几十毫秒，
-- 用 `docker exec psql` 轮询（每次 ~100ms 起）只能采到零星几个点，
-- 根本抓不到「20 次扣减之间的中间态」。
-- 触发器在数据库进程内同步执行，每一次 UPDATE 都必然留下一行 —— 无法造假。
--
-- ★ 关键：AFTER UPDATE FOR EACH ROW，记录的是每一行的「新值」。
--   主组应该恰好留下 N_sku 行（每个 SKU 一次）；
--   对照组应该留下 N_sku * 20 行（同一 SKU 被扣 20 次）。
-- ============================================================================

DROP TRIGGER IF EXISTS trg_pay13_stock_audit ON inventories;
DROP TABLE   IF EXISTS pay13_stock_audit;

CREATE TABLE pay13_stock_audit (
    id        BIGSERIAL   PRIMARY KEY,
    sku_id    BIGINT      NOT NULL,
    available INTEGER     NOT NULL,
    locked    INTEGER     NOT NULL,
    sold      INTEGER     NOT NULL,
    at        TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE OR REPLACE FUNCTION fn_pay13_stock_audit() RETURNS trigger AS $$
BEGIN
    INSERT INTO pay13_stock_audit (sku_id, available, locked, sold)
    VALUES (NEW.sku_id, NEW.available_stock, NEW.locked_stock, NEW.sold_stock);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_pay13_stock_audit
    AFTER UPDATE ON inventories
    FOR EACH ROW
    EXECUTE FUNCTION fn_pay13_stock_audit();

SELECT 'audit ready' AS status, count(*) AS pending_rows FROM pay13_stock_audit;
