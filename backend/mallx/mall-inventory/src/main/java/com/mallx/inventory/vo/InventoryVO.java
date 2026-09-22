package com.mallx.inventory.vo;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/**
 * 库存行（{@code GET /api/admin/inventory/skus} 的 records 元素）。
 *
 * <p>★ 四格数字<b>全部给出</b>（{@code total} / {@code available} / {@code locked} / {@code sold}），
 * 一个都不省 —— 因为管理端看库存时，脑子里算的正是那条恒等式：
 * <pre>
 *   total_stock = available_stock + locked_stock + sold_stock
 * </pre>
 * 只给 {@code available}（像 C 端商品页那样）就没法自查这条式子；
 * 而「能不能自查」正是本日验收里 {@code [7]} 那组断言（四格数字与 DB 逐格一致）的前提。
 *
 * <p>★ {@code skuName} / {@code productName} 来自
 * {@code LEFT JOIN product_skus s} + {@code LEFT JOIN products p} ——
 * 运营不可能记住「SKU 4 是什么」，库存列表必须自解释。
 * 这里的 JOIN 是<b>只读跨表查询</b>，不是模块依赖
 * （与本项目 {@code PaymentMapper.xml} JOIN {@code orders} 同一性质）。
 *
 * <p>⚠️ 用作 {@code resultType} 时必须有无参构造：框架走「反射无参构造 + setter」。
 * {@code @NoArgsConstructor} 是显式把它钉住（`@Data` 只在类里没有别的构造函数时才补默认构造）。
 * 这个坑编译期不报错，只有真正查库时才炸 {@code ReflectionException}。
 *
 * <p>⚠️ 别把 {@code Inventory} 实体直接当出参：它没有 SKU 名 / 商品名，
 * 而且实体是「表结构的镜像」——表加一列，接口出参就跟着变，
 * 那正是「出参白名单」要防的事。显式列一遍，成本很低。
 */
@Data
@NoArgsConstructor
public class InventoryVO {

    private Long skuId;

    /** SKU 名（如「黑色 256GB」），来自 product_skus.name */
    private String skuName;

    private Long productId;

    /** 商品名（如「Apple iPhone 17 Pro」），来自 products.name */
    private String productName;

    private Integer totalStock;

    private Integer availableStock;

    private Integer lockedStock;

    private Integer soldStock;

    private LocalDateTime updatedAt;
}
