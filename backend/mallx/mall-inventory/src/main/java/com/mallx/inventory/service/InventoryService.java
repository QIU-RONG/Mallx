package com.mallx.inventory.service;

/**
 * 库存服务
 *
 * <p>目前只暴露下单所需的「扣减」能力。支付成功后的 {@code locked → sold}、
 * 取消订单的 {@code locked → available} 回补，留到 Day 13/14 支付与订单状态机时再加。
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
}
