package com.mallx.order.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.mallx.order.api.OrderItemBuyContext;
import com.mallx.order.entity.OrderItem;
import org.apache.ibatis.annotations.Param;

/**
 * 订单明细 Mapper
 *
 * <p>★ 写入与常规查询仍由 {@link BaseMapper} 覆盖（{@code insert} 下单、
 * {@code selectList} 查详情），那部分确实<b>不需要 XML</b>。
 *
 * <p>★★ 但 <b>Day 16 起本接口有了第一条自定义 SQL</b>：{@link #selectBuyContext}
 * —— 它要 JOIN {@code orders} 拿订单状态、并在 {@code WHERE} 里做归属校验，
 * 这两件事 {@code BaseMapper} 都表达不了。
 * ⇒ XML 落在 {@code src/main/resources/mapper/OrderItemMapper.xml}（本文件对应的
 * <b>新</b>XML，此前 {@code mapper/} 目录下只有 {@code OrderMapper.xml}）。
 *
 * <p>⚠️ XML 的三条铁律（Day 05 起就没变过）：
 * <ol>
 *   <li>必须放 {@code src/main/resources/mapper/} —— 放在 {@code src/main/java} 下 Maven 不复制；</li>
 *   <li>{@code mapper-locations} 已配成 {@code classpath*:} + {@code mapper/} 下的通配
 *       （<b>星号不能省</b>，否则扫不到兄弟模块 jar 里的 XML）；</li>
 *   <li>方法名与 XML 的 {@code id} <b>逐字符一致</b> —— 差一个字母就在调用时报
 *       {@code Invalid bound statement (not found)}，<b>编译期不报错</b>。</li>
 * </ol>
 *
 * <p>不加 {@code @Mapper} 注解：全局 {@code @MapperScan("com.mallx.**.mapper")} 已覆盖本包。
 */
public interface OrderItemMapper extends BaseMapper<OrderItem> {

    /**
     * ★★ 供别的模块（当前是 {@code mall-review}）调用：按「订单明细 id」取出这笔购买的事实。
     *
     * <p>★★ 返回 {@code null} 的语义被<b>故意</b>压成一种：<b>「不存在」或者「不是你的」</b>。
     * 归属条件写在 SQL 的 {@code WHERE o.user_id = #{userId}} 里 ——
     * 两种原因在数据库层就合成了一个空结果，调用方拿到的结论天然不可区分
     * （与订单详情 / 支付记录 / 评价各处的 404 伪装是同一条原则）。
     * ★ 本方法被<b>别的模块</b>调用，所以防线必须写死在 SQL 里，不能靠调用方自觉。
     *
     * <p>★ 为什么 {@code userId} 必须 {@code @Param}：多参数方法在 MyBatis 里
     * 默认叫 {@code arg0/param1}，XML 写 {@code #{userId}} 会解析不到。
     * （即使只有一个参数也建议写上 —— 少一个隐性约定。）
     *
     * <p>⚠️ 本方法<b>只读</b>：不写任何表、不加锁、不需要事务。
     *
     * @param userId      当前登录用户（来自 token，绝不接受客户端传参）
     * @param orderItemId 订单明细 id（唯一由客户端提供的标识）
     * @return 这笔购买的事实；明细不存在<b>或</b>不属于该用户 → {@code null}
     */
    OrderItemBuyContext selectBuyContext(@Param("userId") Long userId,
                                         @Param("orderItemId") Long orderItemId);
}
