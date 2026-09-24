package com.mallx.marketing.common;

/**
 * {@code user_coupons.status} 的取值常量 —— 与 {@code CouponType} 同一种做法。
 *
 * <p>★ 为什么需要它：{@code user_coupons.status} 列是
 * {@code VARCHAR(30) NOT NULL DEFAULT 'UNUSED'}，<b>没有 CHECK 约束</b>
 * → 取值写错了数据库一声不吭。所以「合法的取值集合」只能由应用层表达，
 * 并且写成常量而不是散落的字符串字面量。
 *
 * <p>★★ <b>状态机（Day 21 起变成<b>双向</b>的）</b>：
 * <pre>
 *   UNUSED ──(下单：核销)──▶ USED
 *     ▲                       │
 *     └──(取消订单：退券)─────┘
 * </pre>
 * Day 20 只有第一步（UNUSED 是唯一写入值，写死在 {@code insertIgnore} 的 SQL 里）；
 * Day 21 加了反向的一步 —— 而「能正着走也能倒着走」正是阶段二比阶段一难的地方：
 * 正向只需要把券改成 USED，反向还要把 {@code order_id} / {@code used_at} <b>清干净</b>，
 * 否则这张券会一直挂着一个已经取消的订单号。
 *
 * <p>⚠️ {@code EXPIRED} <b>刻意不在这里定义</b> —— 它不是「可以写进去的值」。
 * 本项目对「过期」的一贯做法是<b>惰性计算</b>：查询时拿
 * {@code coupons.end_time} 与 {@code CURRENT_TIMESTAMP} 比，<b>不写回数据库</b>
 * （见 {@code UserCouponVO#expired} 与 Day 20 的取舍说明）。
 * 把它放进这个类，等于给后来者一个「这里可以写 EXPIRED」的错误暗示。
 * <ul>
 *   <li>代价：每次查询多一个时间比较 —— 可接受；</li>
 *   <li>收益：零调度、零副作用、脚本可无限重跑，不需要为一个定时写点单独维权。</li>
 * </ul>
 * ★ 若哪天真的引入定时任务把 EXPIRED 落库，那是<b>一次状态机扩张</b>：
 * {@code selectMyCoupons} 的 {@code expired} 计算、以及依赖它的断言都要同步改
 * （否则那条断言会一直绿，却不再证明任何事）。
 */
public final class UserCouponStatus {

    /** 已领取、未使用 —— 唯一「可用」的状态 */
    public static final String UNUSED = "UNUSED";

    /** 已核销：已挂到某张订单上（{@code order_id} / {@code used_at} 非空） */
    public static final String USED = "USED";

    private UserCouponStatus() {
    }

    /** 供 Service 判断「这张券还能不能用」；不含 null 检查（该列 NOT NULL，实体字段为 null 属异常） */
    public static boolean isUsable(String status) {
        return UNUSED.equals(status);
    }
}
