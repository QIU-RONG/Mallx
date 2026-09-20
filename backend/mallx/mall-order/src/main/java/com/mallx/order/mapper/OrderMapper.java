package com.mallx.order.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.mallx.order.entity.Order;
import com.mallx.order.vo.AddressForOrderVO;
import com.mallx.order.vo.OrderItemSourceVO;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/**
 * 订单 Mapper
 *
 * <p>{@link BaseMapper} 提供单表 CRUD（第 4 步的分页 {@code selectPage} 也用它）；
 * 跨模块 / 跨表的语句一律走 XML。
 *
 * <p>⚠️ 铁律：这里声明的每个方法，{@code OrderMapper.xml} 里必须有【方法名逐字符一致】的
 * 同名标签，否则 MyBatis 启动时不报错、一调用就 {@code Invalid bound statement}。
 * 现有七个（都在 XML 里）：
 * {@code selectAddressForOrder} / {@code selectSelectedCartItems} / {@code deleteSelectedCartItems}
 * / {@code markPaid} / {@code cancelOrder} / {@code shipOrder} / {@code confirmReceipt}。
 *
 * <p>★ {@code markPaid} 与 {@code cancelOrder} 是「同一条边的两个方向」：都是
 * {@code WHERE status = 'PENDING_PAYMENT'}，一个走向 {@code PAID}、一个走向 {@code CANCELLED}。
 *
 * <p>★ {@code shipOrder} / {@code confirmReceipt} 是 Day 15 补上的正向两条边
 * （{@code PAID → SHIPPED → COMPLETED}）：两者都<b>不碰库存</b>，
 * 且起点各不相同 —— 所以它们不与支付/取消抢状态位，只能按顺序发生。
 * 这也是本文件里唯一两条「起点不是 {@code PENDING_PAYMENT}」的语句。
 *
 * <p>不加 {@code @Mapper} 注解：全局 {@code @MapperScan("com.mallx.**.mapper")} 已覆盖本包。
 */
public interface OrderMapper extends BaseMapper<Order> {

    /**
     * 读收货地址 —— IDOR 校验直接写在 WHERE 里。
     *
     * @return {@code null} 表示「地址不存在【或】不是你的」—— 两种情况调用方统一返 404，
     * 绝不能说「这不是你的地址」（那等于告诉攻击者这个 id 是有效资源）
     */
    AddressForOrderVO selectAddressForOrder(@Param("addressId") Long addressId,
                                            @Param("userId") Long userId);

    /**
     * 读购物车里【已勾选】的项，跨表带出商品/规格/库存现场。
     *
     * <p>★ 故意 {@code LEFT JOIN} 且不过滤 {@code is_deleted} —— 失效项也要查得出来去报错，
     * 悄悄消失的后果是「用户以为买了 5 件，只收到 4 件」。
     */
    List<OrderItemSourceVO> selectSelectedCartItems(@Param("userId") Long userId);

    /** 清掉已勾选的购物车项（下单成功的最后一步）。返回删除行数，供日志/断言 */
    int deleteSelectedCartItems(@Param("userId") Long userId);

    /**
     * 支付成功：CAS 推进订单状态 —— 条件 UPDATE 在本项目的第三次使用
     * （前两次：{@code inventories.deductStock} 扣库存、{@code moveLockedToSold} 转已售）。
     *
     * <p>★ 为什么不是「先查后改」：两个线程都先读到 {@code PENDING_PAYMENT}，
     * 就会各自 UPDATE 一次 → <b>收两笔钱</b>。{@code WHERE status = 'PENDING_PAYMENT'}
     * 让数据库替我们做原子比较：只有第一个匹配得上，第二个执行时状态已变 → 0 行。
     *
     * <p>★★ {@code orders} 表<b>没有 version 列</b> —— 所以「状态字段自己就是版本号」。
     * 这也是本方法不需要任何乐观锁工具的原因。
     *
     * <p>★ 为什么 {@code WHERE} 里【不要再带 user_id】：归属已在支付 Service 第一步
     * （{@code SELECT … WHERE id = ? AND user_id = ?}）验完。带了会让
     * 「订单不存在 / 不是你的 / 状态不对」三种 0 行原因重新糊在一起，
     * 上层就没法把它稳定地翻成「400 状态不允许支付」。
     *
     * @param orderId 订单主键
     * @return 影响行数：1 = 抢到了；0 = 已被别人先付 / 已取消（状态不是 {@code PENDING_PAYMENT}）
     */
    int markPaid(@Param("orderId") Long orderId);

    /**
     * 取消成功：CAS 推进订单状态 —— 条件 UPDATE 在本项目的第四次使用
     * （前三次：{@code deductStock} 扣库存、{@code moveLockedToSold} 转已售、{@code markPaid} 标记已付）。
     *
     * <p>★★ 与 {@link #markPaid} 是<b>同一条边的两个方向</b>：同一个
     * {@code WHERE status = 'PENDING_PAYMENT'}、同一个起点，只是一个走向 {@code PAID}、
     * 一个走向 {@code CANCELLED}。两条出路<b>互斥</b> ——
     * 这正是「取消与支付并发时只有一个能成功」在 SQL 层的全部保证。
     *
     * <p>★ 为什么不是「先查后改」：两个线程都先读到 {@code PENDING_PAYMENT}，
     * 各自 UPDATE 一次 → <b>既收了钱又把货退回可售池</b>（同一件货凭空变两件）。
     *
     * <p>★ 为什么 {@code WHERE} 里【不要再带 user_id】：归属已在 Service 第一步
     * （{@code requireOwn}）验完。带了会让「订单不存在 / 不是你的 / 状态不对」
     * 三种 0 行原因重新糊在一起，上层就没法稳定地把它翻成「400 状态不允许取消」。
     *
     * <p>★ {@code cancelled_at} 是本列<b>第一次被写入</b>（此前全为 NULL）——
     * 与 {@code paid_at} 一样由 SQL 手写，不挂自动填充：它记的是业务事实发生的那一刻，
     * 不是「这一行被改过」。
     *
     * @param orderId 订单主键
     * @return 影响行数：1 = 抢到了；0 = 已被别人先付 / 已取消（状态不是 {@code PENDING_PAYMENT}）
     */
    int cancelOrder(@Param("orderId") Long orderId);

    /**
     * 查「超时未支付」的订单 id（Day 14 第 3 步 · 超时关单）。
     *
     * <p>★★ <b>不带 user_id 条件</b> —— 这是本方法与其它所有查询最大的不同。
     * 定时任务代表的是<b>系统</b>，它有权取消任何人的超时单；
     * 用户视角的 {@code cancel} 才需要 {@code requireOwn} 那道归属校验。
     * 把两者混成一个方法，要么越权，要么系统取消不了。
     *
     * <p>★ 为什么只返回 {@code id} 而不是整行 {@code Order}：
     * 调用方拿到 id 就去逐单开事务，这些行的其它字段一个都不会看 ——
     * 拖整行纯属浪费（而且要再定义 VO 或复用实体）。
     *
     * <p>★ {@code ORDER BY id}：让批量处理顺序稳定、可复现，
     * 与库存扣减「按 skuId 升序」是同一个理由（统一顺序 → 无环形等待）。
     *
     * <p>★ 判据只看 {@code created_at}，不引入任何「超时标记列」——
     * 状态 + 时间就是全部依据，不需要额外的 DDL（本步零 DDL）。
     *
     * @param minutes 超时阈值（分钟）：{@code created_at} 早于「现在 − minutes」的待支付单
     * @return 超时订单 id 列表（按 id 升序）；无超时单时返回空列表，不是 null
     */
    List<Long> selectTimeoutOrderIds(@Param("minutes") int minutes);

    /**
     * 发货：CAS 推进订单状态（Day 15 第 1 步）—— 条件 UPDATE 在本项目的第五次使用
     * （前四次：{@code deductStock}、{@code moveLockedToSold}、{@code markPaid}、{@code cancelOrder}）。
     *
     * <p>★ 为什么不是「先查后改」：两个线程都先读到 {@code PAID}，
     * 各自 UPDATE 一次 → <b>同一张单被发了两次货</b>，还会各写一次 {@code shipped_at}。
     * {@code WHERE status = 'PAID'} 让数据库替我们做原子比较：
     * 只有第一个匹配得上，第二个执行时状态已变 → 0 行。
     *
     * <p>★★ 与前四条边最大的不同：<b>本方法不碰库存</b>。
     * 「货」的归属在支付那一刻（{@code locked → sold}）就已经定死了 ——
     * 发货推进的是<b>物流状态</b>，{@code available / locked / sold} 三格一格不动。
     * 所以本方法既没有第二个写点需要事务保护，也不写 {@code inventory_logs} 流水。
     *
     * <p>★ 起点 {@code PAID}、终点 {@code SHIPPED} —— 这是状态机里<b>唯一一条起点不是
     * {@code PENDING_PAYMENT} 的边</b>。因此它与支付/取消的互斥关系不同：
     * 那两条边抢同一个状态位（谁快谁赢），本边只能<b>按顺序</b>排在支付成功之后。
     *
     * <p>★ 【故意不做】归属校验：这是<b>管理端动作</b>（权限 {@code order:ship}），
     * 管理员有权给任何人的订单发货 —— 所以本方法<b>不接收 userId</b>，
     * {@code WHERE} 里也只有 {@code id}。订单存不存在统一由 0 行表达。
     *
     * <p>★ {@code shipped_at} 由 SQL 手写（不挂 fill）—— 与 {@code paid_at} 一样，
     * 它记的是「业务事实发生的那一刻」，不是「这一行被改过」。
     *
     * @param orderId 订单主键
     * @return 影响行数：1 = 抢到了；0 = 订单不存在 / 已被别人先发货 / 状态不是 {@code PAID}
     */
    int shipOrder(@Param("orderId") Long orderId);

    /**
     * 确认收货：CAS 推进订单状态（Day 15 第 2 步）—— 条件 UPDATE 在本项目的第六次使用。
     *
     * <p>★ 与 {@link #shipOrder} 是<b>三处相反</b>的孪生：
     * 本方法是 <b>C 端用户动作</b> —— 要归属分流（Service 层 {@code requireOwn}）、
     * 不挂 {@code @PreAuthorize}、起点是 {@code SHIPPED} 而不是 {@code PAID}。
     *
     * <p>★ 为什么不是「先查后改」：两个线程都先读到 {@code SHIPPED}，
     * 各自 UPDATE 一次 → <b>重复确认收货</b>。{@code WHERE status = 'SHIPPED'}
     * 让数据库替我们做原子比较：只有第一个匹配得上，第二个执行时状态已变 → 0 行。
     *
     * <p>★ 与 {@link #shipOrder} 一样<b>不碰库存</b>：{@code available / locked / sold}
     * 三格一格不动，因此同样不需要事务与库存流水。
     *
     * <p>★ 为什么 {@code WHERE} 里【不要再带 user_id】：归属已在 Service 第一步
     * （{@code requireOwn}）验完。带了会让「订单不存在 / 不是你的 / 状态不对」
     * 三种 0 行原因重新糊在一起，上层就没法把它稳定地翻成「400 状态不允许确认收货」。
     *
     * <p>★ {@code completed_at} 是本列<b>第一次被写入</b>（此前全为 NULL）——
     * 同样由 SQL 手写，不挂 fill。
     *
     * @param orderId 订单主键
     * @return 影响行数：1 = 抢到了；0 = 订单不存在 / 已被别人确认过 / 状态不是 {@code SHIPPED}
     */
    int confirmReceipt(@Param("orderId") Long orderId);
}
