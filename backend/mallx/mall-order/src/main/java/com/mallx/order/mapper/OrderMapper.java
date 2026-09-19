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
 * 跨模块 / 跨表的四条语句走 XML。
 *
 * <p>⚠️ 铁律：这里声明的每个方法，{@code OrderMapper.xml} 里必须有【方法名逐字符一致】的
 * 同名标签，否则 MyBatis 启动时不报错、一调用就 {@code Invalid bound statement}。
 * 现有四个（都在 XML 里）：
 * {@code selectAddressForOrder} / {@code selectSelectedCartItems} / {@code deleteSelectedCartItems}
 * / {@code markPaid}。
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
}
