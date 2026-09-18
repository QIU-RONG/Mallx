package com.mallx.cart.vo;

import lombok.Data;

import java.math.BigDecimal;
import java.util.List;

/**
 * 购物车整体视图。
 *
 * <p>★ 口径约定（故意的，别改）：
 * <ul>
 *   <li>{@code totalQuantity} —— <b>所有行</b>（含失效项）quantity 之和；</li>
 *   <li>{@code selectedQuantity / selectedAmount} —— 只算「<b>有效 且 已勾选</b>」的行，
 *       失效项即使 selected=true 也不计入（否则用户会为买不到的东西付钱）。</li>
 * </ul>
 */
@Data
public class CartVO {

    private List<CartItemVO> items;

    /** 所有行（含失效项）quantity 之和 */
    private Integer totalQuantity;

    /** ★ 有效且勾选 的 quantity 之和 */
    private Integer selectedQuantity;

    /** ★ 有效且勾选 的小计之和（= 结算金额预览） */
    private BigDecimal selectedAmount;
}
