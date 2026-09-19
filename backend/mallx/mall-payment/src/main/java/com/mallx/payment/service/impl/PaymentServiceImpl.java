package com.mallx.payment.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.mallx.common.api.PageResult;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.inventory.service.InventoryService;
import com.mallx.order.entity.Order;
import com.mallx.order.entity.OrderItem;
import com.mallx.order.mapper.OrderItemMapper;
import com.mallx.order.mapper.OrderMapper;
import com.mallx.order.service.OrderService;
import com.mallx.payment.common.PaymentMethod;
import com.mallx.payment.common.PaymentStatus;
import com.mallx.payment.dto.PaymentCreateDTO;
import com.mallx.payment.entity.Payment;
import com.mallx.payment.mapper.PaymentMapper;
import com.mallx.payment.service.PaymentService;
import com.mallx.payment.vo.PaymentVO;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ThreadLocalRandom;

/**
 * 支付服务实现 —— ★★★ Day 13 的核心类。
 *
 * <p>一句话概括它做的两件事：
 * <ol>
 *   <li><b>语义分流</b>：先查（归属条件写在 WHERE 里）→ 把「不存在 / 不是你的」
 *       伪装成同一个 {@code 404}；</li>
 *   <li><b>并发防重</b>：再 CAS（{@code WHERE status = 'PENDING_PAYMENT'}）→
 *       0 行说明状态不对，报 {@code 400}。</li>
 * </ol>
 *
 * <p>★★ 这两步<b>不能合并成一条条件 UPDATE</b>：合并之后就分不清「订单不存在」与
 * 「状态不对」了 —— 前者必须 404（且不能泄露存在性），后者必须 400（要明说原因）。
 * <b>先用 SELECT 定身份，再用 UPDATE 定胜负。</b>
 *
 * <p>★ 事务：{@code pay} 是唯一的事务边界。它调用的 {@code orderService} /
 * {@code inventoryService} 都是<b>同一个 JVM 里的普通 Spring Bean 调用</b>
 * （跨模块但同类加载器），{@code @Transactional} 默认传播 REQUIRED →
 * 自动加入本事务，不需要任何额外配置。
 */
@Service
public class PaymentServiceImpl implements PaymentService {

    /**
     * 支付方式白名单：DTO 的 {@code @Pattern} 是<b>第一道</b>，这里是<b>第二道</b>。
     *
     * <p>防的不是 HTTP 请求（那个已经被 {@code @Valid} 拦了），而是将来别的调用方
     * （定时任务 / 管理端 / 测试代码）<b>绕开 Controller 直接调 Service</b>。
     * {@code payments.method} 列没有 CHECK 约束，脏值落库就只能靠这种白名单挡住。
     */
    private static final Set<String> ALLOWED_METHODS =
            Set.of(PaymentMethod.ALIPAY, PaymentMethod.WECHAT, PaymentMethod.BALANCE);

    /**
     * 分页上限：单页最多 100 条 —— 与 {@code OrderServiceImpl.MAX_PAGE_SIZE} 同一个值。
     *
     * <p>★ 为什么不抽到 mall-common 做成公共常量：那是一次跨模块重构（牵动 order / payment
     * 两个模块的既有代码），与本步「新增查询接口」无关。两处各留一份、注释互相指明，
     * 等真有第三个模块需要时再抽。
     */
    private static final long MAX_PAGE_SIZE = 100;

    private final PaymentMapper paymentMapper;        // mall-payment
    private final OrderMapper orderMapper;            // mall-order
    private final OrderItemMapper orderItemMapper;    // mall-order
    private final OrderService orderService;          // mall-order
    private final InventoryService inventoryService;  // mall-inventory

    public PaymentServiceImpl(PaymentMapper paymentMapper,
                              OrderMapper orderMapper,
                              OrderItemMapper orderItemMapper,
                              OrderService orderService,
                              InventoryService inventoryService) {
        this.paymentMapper = paymentMapper;
        this.orderMapper = orderMapper;
        this.orderItemMapper = orderItemMapper;
        this.orderService = orderService;
        this.inventoryService = inventoryService;
    }

    /**
     * ★★★ 支付主链路 —— 六步全在一个事务里。
     *
     * <p>★ {@code @Transactional} 【不能漏】：④ 成功而 ⑤ 失败时若不回滚，
     * 就留下「订单已支付、库存没转已售」这种钱货对不上账的状态。
     *
     * <p>⚠️ 异常必须【抛出去】：在里面 try-catch 吞掉再 return，事务不会回滚。
     * 统一由 GlobalExceptionHandler 在外层转成 body 里的 code（HTTP 200 + code 是项目约定）。
     *
     * <p>★ {@code rollbackFor = Exception.class} 比裸 {@code @Transactional} 多兜一层
     * 「受检异常」。本项目的 {@code BusinessException} 继承 {@code RuntimeException}，
     * 所以裸注解其实也够（{@code OrderServiceImpl} 就是这么写的）——
     * 显式写出来是防御性，不是必须。
     */
    @Override
    @Transactional(rollbackFor = Exception.class)
    public PaymentVO pay(Long userId, PaymentCreateDTO dto) {

        // ⓪ 支付方式白名单（第二道防线）—— 不碰数据库，先挡下明显非法的入参
        if (!ALLOWED_METHODS.contains(dto.getMethod())) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "支付方式不正确");
        }

        // ① 语义分流：归属条件直接写进 WHERE（不是查回来再用 if 比）—— 查不到就是 404
        Order order = orderMapper.selectOne(new LambdaQueryWrapper<Order>()
                .eq(Order::getId, dto.getOrderId())
                .eq(Order::getUserId, userId));
        if (order == null) {
            // ★★ 「订单不存在」与「订单不是你的」统一 404（IDOR 伪装）：
            //    若两者返回码不同，攻击者遍历 id 就能画出「哪些订单真实存在」的地图。
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "订单不存在");
        }

        // ② 读明细：要转移的是哪几个 SKU、各多少件（只认服务端数据）
        List<OrderItem> items = orderItemMapper.selectList(
                new LambdaQueryWrapper<OrderItem>().eq(OrderItem::getOrderId, order.getId()));
        if (items.isEmpty()) {
            // 正常流程不可能发生（下单那一刻就写了明细）；真发生了说明数据被旁路改过 →
            // 服务端异常态，重试无意义，用 FAIL(500) 而不是 400。
            throw new BusinessException(ResultCode.FAIL.getCode(), "订单明细缺失");
        }

        // ③ 插支付单 —— ★ 金额取服务端 order.getPayAmount()，绝不看请求体
        Payment payment = new Payment();
        payment.setPaymentNo(generatePaymentNo());
        payment.setOrderId(order.getId());
        payment.setAmount(order.getPayAmount());
        payment.setMethod(dto.getMethod());
        payment.setStatus(PaymentStatus.SUCCESS);
        payment.setPaidAt(LocalDateTime.now());   // 业务时间戳手写（不挂 fill）
        paymentMapper.insert(payment);            // ★ 插入后自增 id 回填

        // ④ CAS 抢资格：抢不到就抛异常 → 整个事务回滚 → ③ 插的支付单一起消失。
        //    ★ 放在 ⑤ 之前：④ 是「抢资格」，抢不到就没必要去动库存（少做无用功）。
        orderService.markPaid(order.getId());

        // ⑤ 逐个 SKU 把 locked 搬进 sold（★★ available_stock 一动不动）
        //    ★ 用 moveLockedToSold 而不是 deductForOrder —— 后者会动 available，
        //      等于把同一件货扣两遍（available 在下单那一刻就已经被扣过了）。
        for (OrderItem item : items) {
            inventoryService.moveLockedToSold(item.getSkuId(), item.getQuantity());
        }

        // ⑥ 组装返回（因为 ③ 的回填，这里 id / paymentNo / paidAt 都是真值）
        return new PaymentVO(payment.getId(), payment.getPaymentNo(), order.getId(),
                order.getOrderNo(), payment.getAmount(), payment.getMethod(),
                payment.getStatus(), payment.getPaidAt());
    }

    // ============================ 查询（Day 13 第 4 步） ============================

    /**
     * ★★ 分页参数夹紧 —— 与 {@code OrderServiceImpl.listMyOrders} 完全同款。
     *
     * <p>★ 夹紧必须在 {@code new Page<>(...)} <b>之前</b>做：
     * 构造进去的值就是最终发给 DB 的值，之后再改局部变量毫无意义。
     *
     * <p>★ 两行的分量不一样（Day 12 实测结论，别讲成一样重）：
     * <pre>
     * size = -1     → MP 特例：size &lt; 0 表示「不执行分页」= 查全表！      → 第一行救命
     * size = 0      → 返回【空列表】但 total 正常（以为没数据，比报错更难发现）→ 第一行救命
     * size = 99999  → LIMIT 99999，一个人一次拖走整张表（DoS）            → 第二行救命
     * page = 0 / -5 → MP 双层兜住（Page 构造仅 current &gt; 1 时赋值；
     *                 offset() 对 current &lt;= 1 直接返 0）→ 实测安然无恙，
     *                 Math.max(page, 1) 只是「防御性规范化」
     * </pre>
     *
     * <p>★ 越权防线（{@code WHERE o.user_id = #{userId}}）写在 XML 里，与本方法的夹紧是
     * <b>两件独立的事</b>：前者防越权，后者防资源滥用。
     */
    @Override
    public PageResult<PaymentVO> listMyPayments(Long userId, long page, long size) {
        long safePage = Math.max(page, 1);
        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);

        // ★ 首参传 IPage，分页插件才会改写这条自定义 SQL；漏传 = 不报错、静默查全表
        IPage<PaymentVO> result =
                paymentMapper.selectMyPayments(new Page<>(safePage, safeSize), userId);

        // SELECT 已经把 payments 的列与 orders.order_no 一次带回来，不需要再 convert
        return PageResult.of(result);
    }

    /**
     * ★ 支付记录详情 —— 归属校验在 SQL 里（{@code AND o.user_id = #{userId}}），
     * Java 侧只负责把 {@code null} 翻译成 404。
     *
     * <p>★★ 两种 null 原因（id 不存在 / 记录属于别人）<b>必须共用同一句消息</b>：
     * 可区分就等于可枚举 —— 攻击者遍历 id 看返回码，就能画出「哪些支付记录真实存在」的地图。
     *
     * <p>★ 报 404 而不是 403：403 等于承认「这条记录真实存在，只是不给你看」。
     */
    @Override
    public PaymentVO detailMyPayment(Long userId, Long paymentId) {
        PaymentVO vo = paymentMapper.selectMyPaymentById(paymentId, userId);
        if (vo == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "支付记录不存在");
        }
        return vo;
    }

    /**
     * 支付流水号：{@code PAY + yyyyMMddHHmmssSSS + 4 位随机}，
     * 如 {@code PAY202609191430151238472}。与 {@code OrderServiceImpl#generateOrderNo} 同一套思路。
     *
     * <p>★ 它<b>拦不住「同一订单付两次」</b>（两次生成的号一定不同），
     * 只保证 payments 行本身不重号 —— 撞号由 {@code payments_payment_no_key} 唯一索引兜底（抛 23505）。
     */
    private String generatePaymentNo() {
        return "PAY"
                + LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMddHHmmssSSS"))
                + String.format("%04d", ThreadLocalRandom.current().nextInt(10_000));
    }
}
