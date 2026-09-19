package com.mallx.order.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.inventory.service.InventoryService;
import com.mallx.order.entity.OrderItem;
import com.mallx.order.mapper.OrderItemMapper;
import com.mallx.order.mapper.OrderMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Comparator;
import java.util.List;

// mall-order/.../service/impl/OrderCancelExecutor.java
@Service
public class OrderCancelExecutor {

    private final OrderMapper orderMapper;
    private final OrderItemMapper orderItemMapper;
    private final InventoryService inventoryService;

    public OrderCancelExecutor(OrderMapper orderMapper, OrderItemMapper orderItemMapper, InventoryService inventoryService) {
        this.orderMapper = orderMapper;
        this.orderItemMapper = orderItemMapper;
        this.inventoryService = inventoryService;
    }
    /**
     * 单笔取消：CAS 改状态 + 逐 SKU 回补库存，各自一个事务。
     * @return true = 真取消了；false = 状态已不是 PENDING_PAYMENT，解释权交给调用方
     */
    @Transactional
    public boolean cancelOne(Long orderId) {
        List<OrderItem> items = orderItemMapper.selectList(
                new LambdaQueryWrapper<OrderItem>().eq(OrderItem::getOrderId, orderId));
        if (items.isEmpty()) {
            throw new BusinessException(ResultCode.FAIL.getCode(), "订单明细缺失");
        }

        // ★ CAS 的 0 行在这里不抛异常 —— 把「该报 400 还是该跳过」交给调用方
        if (orderMapper.cancelOrder(orderId) == 0) {
            return false;
        }

        items.sort(Comparator.comparing(OrderItem::getSkuId));   // 统一锁顺序
        for (OrderItem item : items) {
            // ★ 传 orderId：写进流水 inventory_logs.reference_id，事后能反查「这批货是哪张单退回来的」
            inventoryService.releaseLocked(item.getSkuId(), item.getQuantity(), orderId);
        }
        return true;
    }
}
