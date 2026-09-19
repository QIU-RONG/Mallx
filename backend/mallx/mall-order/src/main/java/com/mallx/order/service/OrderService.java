package com.mallx.order.service;

import com.mallx.common.api.PageResult;
import com.mallx.order.dto.OrderCreateDTO;
import com.mallx.order.vo.OrderDetailVO;
import com.mallx.order.vo.OrderVO;

/**
 * 订单服务
 */
public interface OrderService {

    /**
     * 从购物车下单：把当前用户【已勾选】的购物车项结算成一张订单。
     *
     * <p>整个方法在一个事务里完成：校验地址 → 读选中项 → 失效校验 → 算金额
     * → 按 skuId 升序锁库存 → 插 orders + order_items → 清购物车选中项。
     *
     * @return 新订单 id
     */
    Long createFromCart(Long userId, OrderCreateDTO dto);

    /**
     * 我的订单列表（分页，按创建时间倒序）。
     *
     * <p>★ 只查 {@code user_id = 当前用户} 的行 —— 越权防线写死在 SQL 条件里，
     * 不接受任何来自客户端的「查谁」参数。
     *
     * <p>★ 分页参数由本方法负责夹紧（实测依据见实现类的注释）：
     * <ul>
     *   <li>{@code size < 1} → 当成 1。
     *       ★ 关键是 {@code size < 0}：MyBatis-Plus 把它解读为「不执行分页、查全部」；
     *       而 {@code size = 0} 会返回【空列表】但 total 不变（用户会以为没订单）。</li>
     *   <li>{@code size > 100} → 截到 100（防止一次把整张表拖出来）。</li>
     *   <li>{@code page < 1} → 归一到 1。属防御性规范化 ——
     *       MyBatis-Plus 自身已对 {@code current <= 1} 做了保护，不会因负 offset 报错。</li>
     * </ul>
     *
     * @param page 页码，从 1 开始
     * @param size 每页条数，最终落在 1..100
     */
    PageResult<OrderVO> listMyOrders(Long userId, long page, long size);

    /**
     * 订单详情（订单头 + 明细快照）。
     *
     * <p>★ 「订单不存在」与「订单不属于当前用户」返回同一个 404 ——
     * 若两种情况的响应可区分，攻击者遍历 id 就能画出「哪些订单真实存在」的地图。
     *
     * @throws com.mallx.common.exception.BusinessException code=404 订单不存在
     */
    OrderDetailVO detail(Long userId, Long orderId);

    /**
     * 支付成功：把订单从「待支付」推进到「已支付」（CAS 条件 UPDATE）。
     *
     * <p>★ 条件 UPDATE 而不是「先查后改」—— 并发下两个线程都会先读到
     * {@code PENDING_PAYMENT}，各自 UPDATE 一次就收了<b>两笔钱</b>。
     * 把状态判断放进 {@code WHERE}，由数据库做原子比较，只有一个人能拿到 1 行。
     *
     * <p>★ 不加 {@code @Transactional}：单条 UPDATE 自身即原子，
     * 事务边界由调用方（{@code PaymentServiceImpl.pay}）持有 ——
     * 让「插支付单 + 改订单状态 + 改 N 个 SKU 库存」共处一个事务才有意义。
     *
     * <p>★ 状态不对时抛业务异常（HTTP 200 + body.code=400）。
     * 这里是 400 而不是 500 —— 「订单已经付过了」是用户可理解的正常结果，
     * 刷新一下就能看到正确状态；对比 {@link com.mallx.inventory.service.InventoryService#moveLockedToSold}
     * 的 0 行是「服务端账目不一致」，那才报 500。
     *
     * @throws com.mallx.common.exception.BusinessException code=400 订单状态不允许支付
     */
    void markPaid(Long orderId);
}
