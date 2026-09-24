package com.mallx.order.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.inventory.service.InventoryService;
import com.mallx.marketing.service.CouponService;
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
    private final CouponService couponService;

    public OrderCancelExecutor(OrderMapper orderMapper, OrderItemMapper orderItemMapper, InventoryService inventoryService, CouponService couponService) {
        this.orderMapper = orderMapper;
        this.orderItemMapper = orderItemMapper;
        this.inventoryService = inventoryService;
        this.couponService = couponService;
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
        // ★★ 退券（Day 21）—— 这一行【必须】在 `cancelOrder` 的 CAS 抢到之后（上面那个 return false 之下）。
        //    放到 CAS 之前就是一条静默的 race：定时关单那条边（cancelTimeoutOrders → cancelOne）
        //    在「订单刚被用户付掉、CAS 返回 0 行」的路径上会照样走到这里、照样退券成功，
        //    而它【不抛异常、事务正常提交】⇒ 落库结果 = 用户既享了折扣、又拿回了券。
        //    （用户视角的 cancel 边会因返回 false 抛 400 触发回滚，所以只有定时任务那条边会真落库。）
        //  ★ 返回值 0 是【正常】的（这一单没用券）⇒ 不当失败处理，也不抛异常。
        couponService.releaseByOrder(orderId);
        return true;
    }
}
