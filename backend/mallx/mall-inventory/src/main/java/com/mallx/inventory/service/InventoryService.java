package com.mallx.inventory.service;

/**
 * 库存服务
 *
 * <p>Day 12 暴露了下单扣减（{@code available → locked}）；
 * Day 13 增加支付成功后的 {@code locked → sold}。
 * 取消订单的 {@code locked → available} 回补留到 Day 14 的订单状态机。
 */
public interface InventoryService {

    /**
     * 下单扣减：把 {@code quantity} 个从可售挪进锁定。
     *
     * <p>库存不足时抛业务异常（HTTP 200 + body.code=400，本项目约定 —— 判成功看 code）。
     *
     * @param skuId    SKU 主键
     * @param quantity 扣减数量（必须 &gt; 0）
     */
    void deductForOrder(Long skuId, int quantity);

    /**
     * 支付成功：把 {@code quantity} 个从锁定挪进已售。
     *
     * <p>★ 只动 {@code locked_stock} 和 {@code sold_stock}，<b>{@code available_stock} 不变</b>。
     * 调用方（支付服务）持有的订单必须仍处于「待支付」—— 这是「一单只付一次」在库存侧的对偶保证。
     *
     * <p>返回 0 行意味着锁定库存不够（订单与库存对不上账），属服务端异常态，
     * 抛业务异常让整笔支付事务回滚。
     *
     * @param skuId    SKU 主键
     * @param quantity 转移数量（必须 &gt; 0）
     */
    void moveLockedToSold(Long skuId, int quantity);
}
