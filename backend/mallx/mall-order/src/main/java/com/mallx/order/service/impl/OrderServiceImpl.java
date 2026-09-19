package com.mallx.order.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.mallx.common.api.PageResult;
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
import com.mallx.order.vo.OrderDetailVO;
import com.mallx.order.vo.OrderItemSourceVO;
import com.mallx.order.vo.OrderItemVO;
import com.mallx.order.vo.OrderVO;
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

    /** 分页上限：单页最多 100 条 —— 防止 ?size=999999 一次把整张 orders 拖出来。 */
    private static final long MAX_PAGE_SIZE = 100;

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

    // ============================ 查询（Day 12 第 4 步） ============================

    /**
     * ★★ 分页参数夹紧 —— 这一行是本步的核心。
     *
     * <p>为什么不夹紧会出三种「变形」（不是「多返回几条」这么温和）：
     * <pre>
     * ?size=99999 → 一个人一次把整张 orders 拖走（DoS）        → Math.min 截到 100
     * ?size=-1    → ⚠️ MyBatis-Plus 特例：size &lt; 0 = 不执行分页 = 查全表！
     *               （见 Page#offset/FEATURE：size&lt;0 时插件直接放行原 SQL）→ Math.max 抬到 1
     * ?page=0     → ⚠️ offset = (0-1)*size = 负数 → PG 报
     *               "OFFSET must not be negative"             → Math.max 抬到 1
     * </pre>
     *
     * <p>★ 夹紧必须在 {@code new Page<>(...)} 【之前】做 —— 构造进去的值就是最终发给 DB 的值，
     * 之后再改 safeSize 这个局部变量毫无意义。
     *
     * <p>★ 另一条防线「只查自己的」写在 wrapper 的 {@code eq(userId)} 里，
     * 和分页参数是两件独立的事：前者防越权，后者防资源滥用。
     */
    @Override
    public PageResult<OrderVO> listMyOrders(Long userId, long page, long size) {
        long safePage = Math.max(page, 1);
        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);

        IPage<Order> result = orderMapper.selectPage(new Page<>(safePage, safeSize),
                new LambdaQueryWrapper<Order>()
                        .eq(Order::getUserId, userId)
                        .orderByDesc(Order::getCreatedAt)
                        // ★ 兜底排序：createdAt 精度可能相同（同一毫秒下的压测订单），
                        //   再按 id 倒序，才能保证分页「不重不漏」而不是随机翻页。
                        .orderByDesc(Order::getId));

        // convert 只做「记录行」的转换（count 不变），返回 IPage<OrderVO>，直接交给 PageResult.of
        return PageResult.of(result.convert(this::toOrderVO));
    }

    @Override
    public OrderDetailVO detail(Long userId, Long orderId) {
        Order order = requireOwn(userId, orderId);

        List<OrderItem> items = orderItemMapper.selectList(
                new LambdaQueryWrapper<OrderItem>()
                        .eq(OrderItem::getOrderId, orderId)
                        .orderByAsc(OrderItem::getId));

        OrderDetailVO vo = new OrderDetailVO();
        vo.setId(order.getId());
        vo.setOrderNo(order.getOrderNo());
        vo.setTotalAmount(order.getTotalAmount());
        vo.setPayAmount(order.getPayAmount());
        vo.setStatus(order.getStatus());
        vo.setReceiverName(order.getReceiverName());
        vo.setReceiverPhone(order.getReceiverPhone());
        vo.setReceiverAddress(order.getReceiverAddress());
        vo.setCreatedAt(order.getCreatedAt());
        vo.setPaidAt(order.getPaidAt());
        vo.setShippedAt(order.getShippedAt());
        vo.setCompletedAt(order.getCompletedAt());
        vo.setCancelledAt(order.getCancelledAt());
        vo.setItems(items.stream().map(this::toItemVO).toList());
        return vo;
    }

    /**
     * 取「我的订单」—— 不是我的，一律伪装成不存在。
     *
     * <p>★★ 为什么「id 不存在」与「id 是别人的」必须返回同一个 404：
     * 若前者 404、后者 403，攻击者只需批量遍历 id 看返回码，
     * 就能画出一张「哪些订单真实存在」的地图（枚举攻击），再配合其它渠道拼出业务规模。
     * 统一 404 = 两种情况在外部【不可区分】。
     *
     * <p>⚠️ 写法：{@code order == null} 必须先判，且 {@code equals} 由实体侧发起 ——
     * {@code userId.equals(order.getUserId())} 在字段为 null 时同样安全，
     * 但用实体侧更贴合「我不存在就没资格谈归属」的语义。
     */
    private Order requireOwn(Long userId, Long orderId) {
        Order order = orderMapper.selectById(orderId);
        if (order == null || !order.getUserId().equals(userId)) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "订单不存在");
        }
        return order;
    }

    /** 订单头 → 列表行（内部分配用的字段如 userId 刻意不外泄） */
    private OrderVO toOrderVO(Order o) {
        OrderVO vo = new OrderVO();
        vo.setId(o.getId());
        vo.setOrderNo(o.getOrderNo());
        vo.setTotalAmount(o.getTotalAmount());
        vo.setPayAmount(o.getPayAmount());
        vo.setStatus(o.getStatus());
        vo.setReceiverName(o.getReceiverName());
        vo.setReceiverPhone(o.getReceiverPhone());
        vo.setReceiverAddress(o.getReceiverAddress());
        vo.setCreatedAt(o.getCreatedAt());
        return vo;
    }

    /** 明细实体 → 明细行（全是快照值，直接搬） */
    private OrderItemVO toItemVO(OrderItem i) {
        OrderItemVO vo = new OrderItemVO();
        vo.setId(i.getId());
        vo.setProductId(i.getProductId());
        vo.setSkuId(i.getSkuId());
        vo.setProductName(i.getProductName());
        vo.setSkuName(i.getSkuName());
        vo.setPrice(i.getPrice());
        vo.setQuantity(i.getQuantity());
        vo.setTotalAmount(i.getTotalAmount());
        vo.setImage(i.getImage());
        return vo;
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
