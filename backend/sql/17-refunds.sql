-- ============================================================
-- MallX · Day 46 退款 / 售后链路（表结构）
-- 说明：需在 01-schema / 02-index / 03-data / 04..16 之后执行。
--       幂等：可重复执行（CREATE ... IF NOT EXISTS）。
-- ============================================================
--
-- ★★ 为什么单独建 refunds 表，而不是给 orders 加两个列：
--   一张订单在售后期里可能经历「申请 → 被拒 → 再申请 → 通过 → 退款」，
--   每一次都是一条<b>有自己生命周期</b>的记录（谁审的、什么时候寄回、物流单号、
--   审核备注）。把这些塞进 orders 的几列里，第二次申请就会覆盖第一次的痕迹 ——
--   而「这张单被拒过几次、为什么」恰恰是售后纠纷里唯一能说清事实的东西。
--
-- ★★ 本文件是【全项目第 25 张表】。
-- ============================================================

CREATE TABLE IF NOT EXISTS refunds (
    id           BIGSERIAL PRIMARY KEY,
    refund_no    VARCHAR(50)   NOT NULL UNIQUE,
    order_id     BIGINT        NOT NULL,
    user_id      BIGINT        NOT NULL,

    -- 售后类型：REFUND_ONLY（仅退款，未发货）/ RETURN_REFUND（退货退款，已发货）
    type         VARCHAR(30)   NOT NULL,

    -- 状态机：APPLIED → APPROVED → (RETURNING → REFUNDING) → SUCCESS
    --               ↘ REJECTED            ↘ CANCELLED
    status       VARCHAR(30)   NOT NULL,

    -- ★ 退款额【快照】：下单那一刻的 orders.pay_amount，不是「现在算出来的」。
    --   V1.0 只支持【全额退款】⇒ 本列恒等于 pay_amount；留成列而不是现查，
    --   是为了让「这单退了多少钱」在订单金额事后被改时仍然可查。
    amount       NUMERIC(12,2) NOT NULL,

    reason       VARCHAR(200),          -- 买家填写的退款原因
    remark       VARCHAR(200),          -- 管理端审核备注（拒绝原因等）
    tracking_no  VARCHAR(50),           -- 退货物流单号（仅 RETURN_REFUND 用）

    created_at   TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- 业务时间戳：不挂 fill，由业务代码在状态流转那一刻手写
    applied_at   TIMESTAMP,             -- 申请
    audited_at   TIMESTAMP,             -- 审核（通过 / 拒绝）
    shipped_at   TIMESTAMP,             -- 买家寄出
    received_at  TIMESTAMP,             -- 卖家确认收货
    refunded_at  TIMESTAMP,             -- 钱退出去

    CONSTRAINT fk_refund_order FOREIGN KEY (order_id) REFERENCES orders(id),
    CONSTRAINT fk_refund_user  FOREIGN KEY (user_id)  REFERENCES users(id)
);

COMMENT ON TABLE  refunds IS '退款/售后单（Day 46）';
COMMENT ON COLUMN refunds.type IS 'REFUND_ONLY=仅退款（未发货）；RETURN_REFUND=退货退款（已发货）';
COMMENT ON COLUMN refunds.status IS 'APPLIED/APPROVED/REJECTED/RETURNING/REFUNDING/SUCCESS/CANCELLED';
COMMENT ON COLUMN refunds.amount IS '退款额快照 = 下单时 orders.pay_amount（V1.0 仅支持全额退款）';

-- ------------------------------------------------------------
-- orders 补丁：退款完成时间戳
-- ------------------------------------------------------------
-- ★ 与 paid_at / shipped_at / completed_at / cancelled_at 同一类：
--   业务时间戳，由 SQL 在状态流转那一刻手写，不挂任何默认值、也不挂填充器。
-- ⚠️ 必须【先落本 DDL，再起应用】：OrderMapper.xml#markRefunded 会写这一列，
--    漏跑补丁的表现是启动正常、一执行退款就报「列不存在」。
ALTER TABLE orders ADD COLUMN IF NOT EXISTS refunded_at TIMESTAMP;

-- ------------------------------------------------------------
-- 索引
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_refunds_user_id  ON refunds (user_id);
CREATE INDEX IF NOT EXISTS idx_refunds_status   ON refunds (status);
CREATE INDEX IF NOT EXISTS idx_refunds_order_id ON refunds (order_id);

-- ★★★ 本表【唯一不能省】的一条约束：一张订单最多只能有一张「还在进行中」的售后单。
--     用 PG 的【部分唯一索引】表达 —— 只有状态落在「进行中」集合里的行才受它管：
--       进行中 = APPLIED / APPROVED / RETURNING / REFUNDING
--     已终结的（SUCCESS / REJECTED / CANCELLED）不受限 ⇒ 售后期结束后
--     （比如订单再次完成）可以重新申请，而不是被一条唯一约束永远锁死。
--
--     ★ 为什么必须落到数据库，而不能只在 Service 里「先查有没有」：
--       那是 TOCTOU —— 用户连点两次提交，两个请求都查到「没有进行中的单」，
--       然后各自插一条 ⇒ 同一张订单凭空出现两张退款单、退两次钱。
--       与 orders 的 markPaid（CAS 条件 UPDATE）、user_coupons 的
--       ON CONFLICT DO NOTHING 是同一个道理：**并发不变式只能由数据库守**。
CREATE UNIQUE INDEX IF NOT EXISTS uk_refunds_active_order
    ON refunds (order_id)
    WHERE status IN ('APPLIED', 'APPROVED', 'RETURNING', 'REFUNDING');

-- ------------------------------------------------------------
-- 自检
-- ------------------------------------------------------------
-- 期望：refunds 表存在、4 个普通索引 + 1 个部分唯一索引（uk_refunds_active_order）
SELECT tablename, indexname, indexdef
  FROM pg_indexes
 WHERE tablename = 'refunds'
 ORDER BY indexname;
