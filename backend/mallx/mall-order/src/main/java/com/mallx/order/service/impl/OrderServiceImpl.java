package com.mallx.order.service.impl;

import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.inventory.service.InventoryService;
import com.mallx.order.common.OrderStatus;
import com.mallx.order.dto.OrderCreateDTO;
import com.mallx.order.entity.Order;
import com.mallx.order.entity.OrderItem;
import com.mallx.order.mapper.OrderItemMapper;
import com.mallx.order.mapper.OrderMapper;
import com.mallx.order.service.OrderService;
import com.mallx.order.vo.AddressForOrderVO;
import com.mallx.order.vo.OrderItemSourceVO;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;

@Service
public class OrderServiceImpl implements OrderService {

    private final OrderMapper orderMapper;
    private final OrderItemMapper orderItemMapper;
    private final InventoryService inventoryService;

    public OrderServiceImpl(OrderMapper orderMapper,
                            OrderItemMapper orderItemMapper,
                            InventoryService inventoryService) {
        this.orderMapper = orderMapper;
        this.orderItemMapper = orderItemMapper;
        this.inventoryService = inventoryService;
    }

    /**
     * ★★★ 全项目第一个「多表写入」方法。
     *
     * <p>{@code @Transactional} 是必须的：⑤~⑦ 任何一步失败都要整体回滚 ——
     * 否则会出现「库存扣了、购物车清了、订单没生成」这种钱货两空。
     *
     * <p>⚠️ 异常必须【抛出去】：在里面 try-catch 吞掉再 return，事务不会回滚。
     * 统一由 GlobalExceptionHandler 在外层转成 body 里的 code（HTTP 200 + code 是项目约定）。
     *
     * <p>★ 跨模块调用 {@link InventoryService} 是同一个 JVM 里的普通 Spring Bean 调用，
     * {@code @Transactional} 默认传播 REQUIRED → 自动加入本方法的事务，不需要额外配置。
     */
    @Override
    @Transactional
    public Long createFromCart(Long userId, OrderCreateDTO dto) {

        // ① 校验地址归属：IDOR 校验写在 SQL 的 WHERE 里（id + user_id）
        AddressForOrderVO addr = orderMapper.selectAddressForOrder(dto.getAddressId(), userId);
        if (addr == null) {
            // 「不存在」与「不是你的」统一 404 —— 不能泄露「这个 id 有效」
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "地址不存在");
        }

        // ② 读购物车【已勾选】项 —— 买什么、买几件只认服务端数据，不认客户端传参
        List<OrderItemSourceVO> sources = orderMapper.selectSelectedCartItems(userId);
        if (sources.isEmpty()) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "请先勾选要购买的商品");
        }

        // ③ 逐项失效判定（顺序复刻 Day 10：先判最根本的原因，且消息里必须带上「是哪件」）
        for (OrderItemSourceVO s : sources) {
            if (Integer.valueOf(1).equals(s.getSkuDeleted())) {
                throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                        "「" + s.getProductName() + "」该规格已删除，请从购物车移除后重试");
            }
            if (Integer.valueOf(1).equals(s.getProductDeleted())) {
                throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                        "「" + s.getProductName() + "」商品已删除，请从购物车移除后重试");
            }
            if (!Integer.valueOf(1).equals(s.getProductStatus())) {
                throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                        "「" + s.getProductName() + "」商品已下架，请从购物车移除后重试");
            }
            if (s.getQuantity() > s.getAvailableStock()) {
                // ⚠️ 这里只是「说人话」的提前提示，不是防线 ——
                //    并发下这一行刚读完，库存就可能被别的事务抢走。
                //    真正的防线是 ⑤ 的条件 UPDATE（WHERE available_stock >= n）。
                throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                        "「" + s.getProductName() + "」库存不足（仅剩 " + s.getAvailableStock() + " 件）");
            }
        }

        // ④ 算总额（服务端算，禁止客户端传金额）：Σ(price × quantity)
        BigDecimal totalAmount = BigDecimal.ZERO;
        for (OrderItemSourceVO s : sources) {
            totalAmount = totalAmount.add(s.getPrice().multiply(BigDecimal.valueOf(s.getQuantity())));
        }

        // ⑤ 扣库存 —— 必须按 skuId 升序，让所有事务按同一顺序取行锁，消灭死锁
        List<OrderItemSourceVO> ordered = new ArrayList<>(sources);
        ordered.sort(Comparator.comparing(OrderItemSourceVO::getSkuId));
        for (OrderItemSourceVO s : ordered) {
            try {
                inventoryService.deductForOrder(s.getSkuId(), s.getQuantity());
            } catch (BusinessException e) {
                // 包一层「是哪件」再抛出。★ 注意是 throw 不是 return ——
                // 只有抛出去的 RuntimeException 才会让整个事务回滚。
                throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                        "「" + s.getProductName() + "」库存不足，请调整数量后重试");
            }
        }

        // ⑥ 插订单 → 拿回填 id → 插明细（快照）
        Order order = new Order();
        order.setOrderNo(generateOrderNo());
        order.setUserId(userId);
        order.setTotalAmount(totalAmount);
        order.setPayAmount(totalAmount);                       // V1.0 无优惠
        order.setStatus(OrderStatus.PENDING_PAYMENT);
        order.setReceiverName(addr.getReceiverName());
        order.setReceiverPhone(addr.getReceiverPhone());
        // 省市区 + 详址拼成一整串（表里就这么设计的，没有三个独立列）
        order.setReceiverAddress(addr.getProvince() + addr.getCity() + addr.getDistrict()
                + addr.getDetailAddress());
        orderMapper.insert(order);                             // ★ 插入后 id 自动回填

        for (OrderItemSourceVO s : sources) {
            OrderItem item = new OrderItem();
            item.setOrderId(order.getId());
            item.setProductId(s.getProductId());
            item.setSkuId(s.getSkuId());
            item.setProductName(s.getProductName());           // ← 以下四行全是快照
            item.setSkuName(s.getSkuName());
            item.setPrice(s.getPrice());
            item.setImage(s.getImage());
            item.setQuantity(s.getQuantity());
            item.setTotalAmount(s.getPrice().multiply(BigDecimal.valueOf(s.getQuantity())));
            orderItemMapper.insert(item);
        }

        // ⑦ 清掉已勾选的购物车项（未勾选的必须留在车里）
        orderMapper.deleteSelectedCartItems(userId);

        return order.getId();
    }

    /**
     * 订单号：{@code MX + yyyyMMddHHmmssSSS + 4 位随机}，如 {@code MX202609191030151238472}。
     *
     * <p>毫秒级 + 4 位随机 → 同一毫秒内还有 1 万种可能；真撞了也有
     * {@code orders_order_no_key} 唯一索引兜底（抛 23505，而不是悄悄写两条同号订单）。
     *
     * <p>⚠️ 这是【够用】不是【生产级】：生产用雪花算法或号段模式（一次从库里领 1000 个号）。
     */
    private String generateOrderNo() {
        return "MX"
                + LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMddHHmmssSSS"))
                + String.format("%04d", ThreadLocalRandom.current().nextInt(10_000));
    }
}
