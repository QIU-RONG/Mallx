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
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;

@Slf4j
@Service
public class OrderServiceImpl implements OrderService {

    /** 分页上限：单页最多 100 条 —— 防止 ?size=999999 一次把整张 orders 拖出来。 */
    private static final long MAX_PAGE_SIZE = 100;

    private final OrderMapper orderMapper;
    private final OrderItemMapper orderItemMapper;
    private final InventoryService inventoryService;

    /**
     * ★ 单笔取消逻辑的持有者（Day 14 第 3 步）。
     *
     * <p>为什么必须是一个<b>独立 Bean</b>，而不是本类的私有方法：
     * 批量入口 {@link #cancelTimeoutOrders} 要「逐单一个事务」，
     * 若它调本类的单笔方法 —— 自调用不走 Spring 代理 → {@code @Transactional}
     * <b>静默失效</b> → 整批共用一个事务，第 37 张单失败会把前 36 张一起回滚。
     *
     * <p>★ 依赖方向是单向的：{@code OrderServiceImpl → OrderCancelExecutor → OrderMapper}。
     * 反过来让 Executor 依赖 OrderService 会形成循环依赖（Spring Boot 默认禁止，启动失败）。
     */
    private final OrderCancelExecutor cancelExecutor;

    public OrderServiceImpl(OrderMapper orderMapper,
                            OrderItemMapper orderItemMapper,
                            InventoryService inventoryService,
                            OrderCancelExecutor cancelExecutor) {
        this.orderMapper = orderMapper;
        this.orderItemMapper = orderItemMapper;
        this.inventoryService = inventoryService;
        this.cancelExecutor = cancelExecutor;
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

    // ============================ 支付（Day 13 第 2 步） ============================

    /**
     * ★★ CAS 推进订单状态 —— 本方法的全部内容就是「调一条条件 UPDATE，看影响行数」。
     *
     * <p>真正的逻辑在 SQL 的 {@code WHERE status = 'PENDING_PAYMENT'} 里（见 OrderMapper.xml）。
     * Java 侧只负责一件事：<b>把 0 行翻译成用户看得懂的话</b>。
     *
     * <p>★ 0 行报 {@code 400} 而不是 {@code 500}：订单「已支付 / 已取消」是业务上的正常状态，
     * 不是系统故障 —— 用户刷新页面就能看到正确状态。
     * （对比 {@code InventoryServiceImpl.moveLockedToSold} 的 0 行是账目对不上，那才报 500。）
     *
     * <p>★ 0 行也<b>不是</b> {@code 404}：订单是否存在已由调用方（PaymentService.pay）
     * 第一步查过，走到这里说明订单一定存在且属于当前用户 ——
     * 所以这里可以安心地说「状态不允许」，不必再含糊其辞。
     *
     * <p>★ 【故意不加】{@code @Transactional}：与 {@code InventoryServiceImpl} 同一个理由 ——
     * 单条 UPDATE 自身即原子，事务边界应由调用方 {@code PaymentServiceImpl.pay} 持有，
     * 好让「插支付单 + 改订单状态 + 改 N 个 SKU」共处一个事务。
     * （若将来加了，默认传播 REQUIRED 也会加入外层事务，行为一致；
     *   但绝不能用 REQUIRES_NEW —— 那等于在支付流程里自己偷偷提交。）
     */
    @Override
    public void markPaid(Long orderId) {
        int rows = orderMapper.markPaid(orderId);
        if (rows == 0) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "订单状态不允许支付");
        }
    }

    // ============== 取消（Day 14 第 1 步 + 第 3 步超时关单） ==============

    /**
     * ★★★ 取消订单（<b>用户视角</b>）—— 与支付链路【严格对称】的四步。
     *
     * <p>把两条链路并排看，取消不是新套路，是支付那条链路的镜像：
     * <pre>
     *              支付（PaymentServiceImpl.pay）        取消（本方法）
     *   ① 归属      SELECT … WHERE id AND user_id       requireOwn（同一句 404 口径）
     *   ② 明细      读 order_items（空 → 500）           同（搬进 cancelOne）
     *   ③ 中间产物  INSERT payments                     无（取消没有「退款单」要写）
     *   ④ 状态 CAS  markPaid   → 0 行 400                cancelOrder → 0 行 400
     *   ⑤ 库存      moveLockedToSold → 0 行 500         releaseLocked → 0 行 500
     *   ⑥ 事务      @Transactional 包 ④⑤                同（外层事务 + cancelOne 加入）
     * </pre>
     *
     * <p>★ ④ 与「支付」的 ④ 是<b>同一个状态位的两次争夺</b>：两条 SQL 的
     * {@code WHERE status = 'PENDING_PAYMENT'} 一模一样，只是 SET 的目标不同。
     * 数据库的行锁 + 条件重求值保证<b>只有一个</b>能拿到 1 行 → 两条出路互斥。
     *
     * <p>★★ ④ 必须在 ⑤ 之前：④ 是「抢资格」。抢不到就没必要去动库存 ——
     * 而且并发时能显著减少对 {@code inventories} 行的锁竞争
     * （只有一个事务会走到 ⑤，其余在 ④ 就被挡下）。
     *
     * <p>★★ ②③④ 的实现搬到了 {@link OrderCancelExecutor#cancelOne(Long)}，因为
     * <b>系统视角</b>（超时关单）要用同一份逻辑，只是对「0 行」的解释不同：
     * 用户视角报 {@code 400}，系统视角<b>跳过</b>（大概率是用户刚好把它付掉了）。
     * 若两边各写一份，第 4 步给库存写点加流水时会漏改其中一处。
     *
     * <p>★ ⑤ 按 {@code skuId} 升序退还，与 {@code createFromCart} 扣减时的排序规则一致。
     * 统一锁顺序才能消灭死锁（环形等待）—— 加锁方向与解锁方向<b>不必</b>相反，
     * 只要所有事务都按同一个顺序拿行锁即可。
     *
     * <p>★ 为什么 {@code cancel} 放在 {@code OrderService} 而不是新开一个服务：
     * 取消只碰 {@code orders} + {@code inventories}，不碰 {@code payments}；
     * 而 {@code mall-order} 本来就依赖 {@code mall-inventory}（下单时就在用 {@code deductForOrder}）。
     * 零新依赖、也不会产生循环依赖。（对比 Day 13 支付必须新开 {@code mall-payment} 模块。）
     *
     * <p>★ 本方法保留 {@code @Transactional}：{@code cancelOne} 是 REQUIRED 传播，
     * 会<b>加入</b>本方法的事务 —— 所以「改状态 + 回补库存」仍然是一个原子操作。
     *
     * @throws com.mallx.common.exception.BusinessException code=404 订单不存在（含「不是你的」）
     * @throws com.mallx.common.exception.BusinessException code=400 订单状态不允许取消
     */
    @Override
    @Transactional
    public void cancel(Long userId, Long orderId) {
        // ① 语义分流：「订单不存在」与「订单不是你的」共用同一个 404（写在 requireOwn 里）
        //    ★ 这是【写操作的 IDOR】—— 读越权是泄露，写越权是破坏，后果更重。
        requireOwn(userId, orderId);

        // ②③④ 与系统视角共用同一份实现（跨 Bean 调用 → 事务正常加入本方法）
        if (!cancelExecutor.cancelOne(orderId)) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "订单状态不允许取消");
        }
    }

    /**
     * ★★ 系统视角：批量取消「超时未支付」的订单（Day 14 第 3 步）。
     *
     * <p>★ 与 {@link #cancel(Long, Long)} 的差别<b>不是少写一行校验</b>，而是<b>权限模型的分层</b>：
     * 前者是「你能取消你的订单」，本方法是「系统有权取消所有人的超时单」——
     * 所以本方法<b>不带 user_id 条件</b>。混成一个方法，要么越权，要么取消不了。
     *
     * <p>★★ 本方法<b>刻意不加 {@code @Transactional}</b>：这是本步最关键的一行「不写」。
     * 整批共用一个事务的话，第 37 张单失败会把前 36 张<b>一起回滚</b>。
     * 逐单事务由 {@link OrderCancelExecutor#cancelOne(Long)} 各自持有。
     *
     * <p>★ 与用户支付的竞态<b>不需要新代码</b>：还是
     * {@code WHERE status = 'PENDING_PAYMENT'} 那条 CAS 兜住 ——
     * 定时任务只是「多了一个竞争者」，谁赢由数据库决定。
     *
     * @param minutes 超时阈值（分钟）
     * @return 本轮<b>真正取消掉</b>的订单条数（0 = 没有超时单，属正常）
     */
    @Override
    public int cancelTimeoutOrders(int minutes) {
        // ① 找出超时未支付的订单 id。★ 不带 user_id —— 这是系统视角
        List<Long> ids = orderMapper.selectTimeoutOrderIds(minutes);
        if (ids.isEmpty()) {
            return 0;                       // 常态：大多数轮次都没有超时单
        }

        // ② 逐单处理 —— ★ 必须走【另一个 Bean】：
        //    若写成 this.cancelOne(...) 就是自调用，不走代理 → @Transactional 静默失效
        int cancelled = 0;
        for (Long id : ids) {
            try {
                // ★ 必须用返回值判断：false = 状态已不是 PENDING_PAYMENT
                //   （大概率是用户刚好付掉了）→ 跳过，不能计成「取消成功」
                if (cancelExecutor.cancelOne(id)) {
                    cancelled++;
                }
            } catch (Exception e) {
                // ★ 必须吞掉（catch Exception 而不是 BusinessException）：
                //   单笔失败不能让后面几十张单失去被取消的机会
                log.warn("超时关单失败，跳过 orderId={}", id, e);
            }
        }
        log.info("超时关单：扫到 {} 张，取消 {} 张", ids.size(), cancelled);
        return cancelled;
    }

    // ==================== 发货 / 确认收货（Day 15 第 1、2 步） ====================

    /**
     * ★★ CAS 推进订单状态 —— 与 {@link #markPaid(Long)} 同构，
     * 本方法的全部内容就是「调一条条件 UPDATE，看影响行数」；
     * 真正的逻辑在 SQL 的 {@code WHERE status = 'PAID'} 里（见 OrderMapper.xml）。
     *
     * <p>★ 0 行报 {@code 400} 而不是 {@code 500}：与支付/取消同一个口径 ——
     * 「订单不是已支付状态」是管理员可理解的正常结果（可能刚被取消、或已经发过货了），
     * 不是服务端账目不一致。
     *
     * <p>★ 0 行也<b>不是</b> {@code 404}：发货<b>不做归属校验</b>，
     * 订单存不存在统一由 0 行表达 —— 管理员不需要（也不应该）从响应里
     * 区分「这个订单号不存在」与「它状态不对」。
     *
     * <p>★ 【故意不加】{@code @Transactional}：本方法<b>只碰 orders 一张表、一条 UPDATE</b>，
     * 自身即原子，没有第二个写点需要与它同生共死。
     * 这正是本日两条边与支付/取消最本质的差别 ——
     * 那两条边要「改状态 + 改 N 个 SKU 库存」，这两条边不碰库存。
     */
    @Override
    public void ship(Long orderId) {
        int rows = orderMapper.shipOrder(orderId);
        if (rows == 0) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "订单状态不允许发货");
        }
    }

    /**
     * ★★ 确认收货（<b>用户视角</b>）—— 与 {@link #cancel(Long, Long)} 同构的两步。
     *
     * <p>把两条链路并排看，本方法就是取消链路的<b>正向孪生</b>：
     * <pre>
     *              取消（cancel）                确认收货（本方法）
     *   ① 归属     requireOwn → 404                同
     *   ② 状态 CAS  WHERE PENDING_PAYMENT          WHERE SHIPPED
     *   ③ 库存      releaseLocked                 无（Day 15 两条边都不碰库存）
     *   ④ 事务      @Transactional 包 ②③           无（只有一条 UPDATE）
     * </pre>
     *
     * <p>★ ① 必须在 ② 之前：② 的 {@code WHERE} 里【不带 user_id】——
     * 带了会让「不存在 / 不是你的 / 状态不对」三种 0 行原因重新糊在一起，
     * 上层就没法把它稳定地翻成「400 状态不允许确认收货」。
     *
     * @throws com.mallx.common.exception.BusinessException code=404 订单不存在（含「不是你的」）
     * @throws com.mallx.common.exception.BusinessException code=400 订单状态不允许确认收货
     */
    @Override
    public void confirm(Long userId, Long orderId) {
        // ① 语义分流：「订单不存在」与「订单不是你的」共用同一个 404（写在 requireOwn 里）
        //    ★ 这是【写操作的 IDOR】—— 读越权是泄露，写越权是破坏，后果更重。
        requireOwn(userId, orderId);

        // ② CAS 抢资格：只有 SHIPPED 才能被确认；0 行 → 400
        int rows = orderMapper.confirmReceipt(orderId);
        if (rows == 0) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "订单状态不允许确认收货");
        }
    }

    // ============================ 查询（Day 12 第 4 步） ============================

    /**
     * ★★ 分页参数夹紧 —— 这一行是本步的核心。
     *
     * <p>为什么要夹紧：不夹紧时 {@code size} 方向会出现【静默变形】（下面全是实测值，不是推理）：
     * <pre>
     * ?size=-1     → ⚠️ MyBatis-Plus 特例：size &lt; 0 表示「不执行分页」= 查全表！
     *                实测：响应 size=-1，返回全部 2 条（夹紧后只有 1 条）
     * ?size=0      → ⚠️ 实测：返回【空列表】（n=0）但 total 仍是 2
     *                —— 用户会以为「我没有订单」，比报错更难发现
     * ?size=99999  → ⚠️ 实测：size 原样回显 99999、未被截断 → LIMIT 99999，
     *                一个人一次把整张 orders 拖走（DoS）
     * </pre>
     *
     * <p>★ 实测【推翻】了一条流行说法：{@code ?page=0} / {@code ?page=-5} 并【不会】造成
     * 负 offset 报错。MyBatis-Plus 有两层保护：
     * <ol>
     *   <li>{@code Page} 的构造函数里 {@code if (current > 1) this.current = current;} —— 否则保持默认 1；</li>
     *   <li>{@code Page#offset()} 对 {@code current <= 1} 直接返回 0。</li>
     * </ol>
     * 实测：{@code ?page=0} → {@code current=1}、{@code n=2}，与不传参完全一致。
     * 所以 {@code Math.max(page, 1)} 是【防御性规范化】（让语义明确），
     * 真正在救命的只有 {@code size} 那一行 —— 别把两行的分量讲成一样重。
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
