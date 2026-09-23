package com.mallx.marketing.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 用户持有的优惠券（{@code user_coupons}）—— 「券」到「人」的<b>领取记录</b>。
 *
 * <p>⚠️ 类名 {@code UserCoupon} 反推的表名是 {@code user_coupon}（少 s）→ <b>必须</b>
 * 显式写 {@code @TableName("user_coupons")}。
 *
 * <p>⚠️ 本表<b>没有</b> {@code is_deleted}、也<b>没有</b> {@code updated_at} —— 禁止加 {@code @TableLogic}，
 * 也别指望自动填充会填什么。它只有一个 DB 默认值可以依赖的列：{@link #receivedAt}。
 *
 * <p>★★ <b>「一人一券」靠 DB 约束，不靠 SELECT 查</b>：
 * <pre>
 *   uk_user_coupons_user_coupon UNIQUE (user_id, coupon_id)
 *   ← 由 backend/sql/09-user-coupons-unique.sql 补上（Day 20），
 *     因为 01-schema.sql 建表时【一个唯一约束都没有】。
 * </pre>
 * 领取时用 {@code INSERT ... ON CONFLICT (user_id, coupon_id) DO NOTHING}，
 * <b>影响行数</b>即答案（1 = 领到 / 0 = 已领过）—— 与 Day 16 评价的写法逐字同构。
 * ⚠️ 没有那个唯一约束时，这条 SQL <b>直接报错</b>（不是静默降级）。
 *
 * <p>★★ <b>状态机（本日只走第一步）</b>：
 * <pre>
 *   UNUSED  ──(阶段二：用券下单)──▶  USED
 *   └─(过期)  ← 本日【不写回】EXPIRED，而是查询时用 coupons.end_time 惰性计算
 * </pre>
 * ★ 为什么不在 DB 里置 {@code EXPIRED}：那需要一个定时扫全表的写点（多一个会改库的东西，
 * 验收时要单独为它维权）。惰性计算零调度、零副作用、可无限重跑。
 * 代价只是每次查询多一个时间比较 —— 阶段二做核销时再重新评估。
 *
 * <p>⚠️ {@link #orderId} 是<b>阶段二</b>（下单抵扣）才写的列，本日一律为 null。
 * 阶段二还要回答一个本阶段刻意避开的问题：<b>订单取消时券要不要退回</b>。
 */
@Data
@TableName("user_coupons")
public class UserCoupon {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** ★ 归属：只能来自 token 的 principal，绝不从请求体读 */
    private Long userId;

    /** 引用 {@code coupons.id}（FK NO ACTION → 有人领过的券删不掉，见 deleteCoupon 的守卫） */
    private Long couponId;

    /** UNUSED / USED / EXPIRED —— 列 VARCHAR(30) NOT NULL DEFAULT 'UNUSED'，<b>无 CHECK 约束</b> */
    private String status;

    /**
     * 领取时间。列是 {@code NOT NULL DEFAULT CURRENT_TIMESTAMP}。
     * ★ 本类的唯一写入口是自定义 XML（{@code insertIgnore}），而<b>自定义 XML 不走填充器</b>
     * → 时间戳必须在 SQL 里手写（本项目 Day 13/16 都栽在这上面）。
     */
    private LocalDateTime receivedAt;

    /** 核销时间（阶段二写） */
    private LocalDateTime usedAt;

    /** 核销订单（阶段二写） */
    private Long orderId;
}
