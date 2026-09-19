package com.mallx.inventory.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.mallx.inventory.entity.Inventory;
import org.apache.ibatis.annotations.Param;

/**
 * 库存 Mapper
 *
 * <p>{@link BaseMapper} 提供全套单表 CRUD；扣库存这种「原子动作」走 XML 手写 SQL。
 *
 * <p>⚠️ 铁律：这里声明的 {@code deductStock}，{@code InventoryMapper.xml} 里必须有同名
 * {@code <update id="deductStock">}，否则 MyBatis 启动时不报错、一调用就
 * {@code Invalid bound statement}。
 *
 * <p>不加 {@code @Mapper} 注解：全局 {@code @MapperScan("com.mallx.**.mapper")} 已覆盖本包。
 */
public interface InventoryMapper extends BaseMapper<Inventory> {

    /**
     * 扣减可售库存并锁入 locked（下单专用）。
     *
     * <p>★ 本方法是「原子动作」，不是「先查后改」：判定条件 {@code available_stock >= quantity}
     * 写在 UPDATE 的 WHERE 里，由数据库在同一条语句内完成「判断 + 扣减」。
     * 调用方通过<b>影响行数</b>得知结果：1 = 扣成功，0 = 库存不足（一行都没改）。
     *
     * @param skuId    SKU 主键
     * @param quantity 扣减数量（必须 &gt; 0）
     * @return 影响行数：1 成功，0 库存不足
     */
    int deductStock(@Param("skuId") Long skuId, @Param("quantity") int quantity);

    /**
     * 把锁定库存转为已售（支付成功专用）。
     *
     * <p>★ 与 {@code deductStock} 是同一招的第二次使用：判定条件 {@code locked_stock >= quantity}
     * 写在 WHERE 里，由数据库在同一条语句内完成「判断 + 转移」，返回<b>影响行数</b>作为答案。
     *
     * <p>★★ 特别注意：<b>{@code available_stock} 一动不动</b>。
     * 这件货在下单那一刻就已经从「可售」挪进「锁定」了，支付只是把它从「锁定」挪到「已售」——
     * 再动一次 available 就等于把同一件货扣两遍。
     *
     * <p>条件里的 {@code locked_stock >= quantity} 是守卫：确保不会把「本来没锁定的货」卖掉。
     * 正常流程永远满足；一旦返回 0，说明订单与库存已经对不上账（数据被旁路改过），
     * 必须整笔事务回滚而不是继续。
     *
     * @param skuId    SKU 主键
     * @param quantity 转移数量（必须 &gt; 0）
     * @return 影响行数：1 成功，0 锁定库存不足（异常态）
     */
    int moveLockedToSold(@Param("skuId") Long skuId, @Param("quantity") int quantity);

    /**
     * 把锁定库存退还可售（取消订单 / 超时关单专用）。
     *
     * <p>★ 本方法是 {@code deductStock} 的<b>严格逆操作</b>：
     * 一个 {@code available → locked}，一个 {@code locked → available}。
     * 到此为止三个库存写点构成完整闭环，恒等式不变量保持：
     * <pre>
     *   deductStock       available - n , locked + n      （下单）
     *   moveLockedToSold  locked - n    , sold + n        （支付）
     *   releaseLocked     locked - n    , available + n   （取消 / 超时）
     * </pre>
     *
     * <p>★★ 守卫是 {@code locked_stock >= quantity}，与 {@code moveLockedToSold} 相同，
     * 而<b>不是</b> {@code available_stock >= quantity}。判据永远是「我要动的那一格够不够」——
     * 本次要动的是 {@code locked}，所以判 {@code locked}。
     * 若误判成 {@code available}，取消一张「从未锁定过货」的订单也能执行成功 →
     * <b>凭空造货</b>。
     *
     * <p>★ 返回 0 行 = 订单说「我锁着 3 件」而库存说「我只锁着 1 件」= 服务端账目不一致，
     * 重试无意义，必须整笔回滚（与 {@code deductStock} 的 0 行 = 用户可控的「库存不足」不同）。
     *
     * @param skuId    SKU 主键
     * @param quantity 退还数量（必须 &gt; 0）
     * @return 影响行数：1 成功，0 锁定库存不足（异常态）
     */
    int releaseLocked(@Param("skuId") Long skuId, @Param("quantity") int quantity);
}
