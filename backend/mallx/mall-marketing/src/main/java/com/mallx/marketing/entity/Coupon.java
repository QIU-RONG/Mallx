package com.mallx.marketing.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 优惠券（{@code coupons}）—— ★ Day 20 建模块，这张表自 Day 03 建表以来<b>第一次被使用</b>。
 *
 * <p>⚠️ 类名 {@code Coupon} 反推的默认表名是 {@code coupon}（少 s）→ <b>必须</b>显式写
 * {@code @TableName("coupons")}，否则所有 SQL 报「表不存在」。
 * 与 {@code Review→reviews} / {@code Order→orders} / {@code Inventory→inventories} 同一个坑
 * （MP 的驼峰转换<b>不做</b>复数→单数，也<b>不加</b> s）。
 *
 * <p>⚠️ 本表<b>没有</b> {@code is_deleted} 列 —— 禁止加 {@code @TableLogic}。
 * 券的「停用」语义由 {@link #status} 承担（1 上架 / 0 下架），删除是物理删
 * （见 {@code CouponServiceImpl.deleteCoupon} 的守卫）。
 *
 * <p>★★ 三个「要理解到位」的字段：
 * <ul>
 *   <li>{@link #type} —— 列是 {@code VARCHAR(30)}，<b>没有 CHECK 约束</b> → 取值只能靠应用层守。
 *       V1.0 两个取值：{@code FIXED}（满减，用 {@link #discountAmount}）/
 *       {@code DISCOUNT}（折扣，用 {@link #discountRate}）。见 {@code common/CouponType}。</li>
 *   <li>{@link #receivedCount} —— 已领取数量。★ 本日是<b>唯一</b>改它的地方（领取时 +1），
 *       且必须是<b>条件 UPDATE</b>（{@code received_count < total_count} 写在 WHERE 里），
 *       绝不「先查后改」—— 见 docs/daily/Day-20-优惠券.md §4.1。</li>
 *   <li>{@link #status} —— 列是 {@code SMALLINT NOT NULL DEFAULT 1}，<b>同样没有 CHECK</b>。
 *       1 = 可领，0 = 下架（下架后既领不到、也不出现在可领列表里）。</li>
 * </ul>
 *
 * <p>★ 时间窗 {@link #startTime} / {@link #endTime} 的判定<b>一律在 SQL 里做</b>
 * （{@code CURRENT_TIMESTAMP} 比较），不搬到 Java —— 见 §4.1 的 CAS 守卫。
 *
 * <p>★ {@code createdAt} / {@code updatedAt} 由 {@code MyMetaObjectHandler} 填充：
 * 管理端发券走 MP 的 {@code save()} → <b>填充器生效</b>。
 * （注意：本模块的 {@code UserCoupon} 走自定义 XML INSERT，那里<b>不走</b>填充器，
 * 但那张表的 {@code received_at} 有 DB 默认值，见该类注释。）
 */
@Data
@TableName("coupons")
public class Coupon {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 券名（列 VARCHAR(100) NOT NULL，<b>无 UNIQUE</b> → 允许重名） */
    private String name;

    /** 券类型：FIXED / DISCOUNT —— 见 {@code common/CouponType}；列无 CHECK 约束 */
    private String type;

    /** 满减金额（{@code NUMERIC(12,2)}，可空）—— type=FIXED 时必填，由 Service 守 */
    private BigDecimal discountAmount;

    /** 折扣率（{@code NUMERIC(5,2)}，可空）—— type=DISCOUNT 时必填，由 Service 守 */
    private BigDecimal discountRate;

    /** 使用门槛（可空）—— 阶段一不参与计算，只作为券面展示信息 */
    private BigDecimal minAmount;

    /** 发行总量（列 NOT NULL DEFAULT 0） */
    private Integer totalCount;

    /** ★ 已领取数量 —— 只由领取的那条条件 UPDATE 改动 */
    private Integer receivedCount;

    /** 可领起始时间（列 NOT NULL，无默认值） */
    private LocalDateTime startTime;

    /** 可领截止时间（列 NOT NULL，无默认值） */
    private LocalDateTime endTime;

    /** 1 = 可领；0 = 下架 */
    private Integer status;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}
