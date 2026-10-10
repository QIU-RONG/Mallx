package com.mallx.aftersale.vo;

import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.NoArgsConstructor;

/**
 * 管理端退款单视图（全站售后列表）—— Day 46。
 *
 * <p>★ 与 {@link RefundVO} 的差别只有两个字段：{@link #orderNo} / {@link #userNickname}。
 * 用继承而不是复制一遍：这两列是<b>纯粹的加法</b>，没有一处需要覆盖或改语义，
 * 复制一份就会出现「给 C 端 VO 加了字段、忘了给管理端加」那类漂移。
 *
 * <p>★ 为什么管理端要看买家昵称：售后是要联系买家的（问退货物流、解释拒绝原因），
 * 列表里没有昵称，运营就得拿着 user_id 去别处查 —— 那是把人肉 JOIN 推给了使用者。
 *
 * <p>⚠️ 昵称必须 {@code COALESCE}：{@code users} 是物理删的表，
 * 万一用户记录没了，JOIN 出来是 null。用 {@code LEFT JOIN} + 兜底串
 * （与 {@code AdminOrderVO} 用<b>同一个</b>兜底串 {@code '用户****'}，前端不用认两种写法）。
 */
@Data
@NoArgsConstructor
@EqualsAndHashCode(callSuper = true)
public class AdminRefundVO extends RefundVO {

    /** 订单号 —— 运营拿它去查订单详情 */
    private String orderNo;

    /** 买家昵称（COALESCE 兜底） */
    private String userNickname;
}
