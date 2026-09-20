package com.mallx.order.api;

import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 跨模块契约对象：一笔购买的「事实」（Day 16 新建）。
 *
 * <p>★★ 为什么单独开一个 {@code api} 包，而不是直接复用 {@code OrderItem} 或 {@code OrderItemVO}：
 * <ol>
 *   <li><b>包名即契约</b>：{@code com.mallx.order.api} 明确宣告「这是给别的模块看的」。
 *       看到它被 import 就知道这是一次<b>跨模块调用</b>，而不是模块内的随手引用。
 *       直接复用实体（{@code OrderItem}）会让消费方跟着本模块的<b>存储细节</b>走 ——
 *       以后给表加列、改列名，跨模块的编译期契约就被动跟着变。</li>
 *   <li><b>字段是按「消费方的提问」裁的</b>：评价模块只问两件事 ——
 *       「这条明细是不是你的？」「这张订单完成了吗？」。所以这里带上了
 *       {@link #orderStatus}（订单域的状态），而 {@code price} / {@code quantity}
 *       这些评价用不到的字段一律不带。</li>
 *   <li><b>带上快照</b>：{@link #productName} / {@link #skuName} / {@link #image} 是
 *       下单那一刻写进 {@code order_items} 的快照值 —— 评价列表直接拿它展示，
 *       不必回 {@code products} / {@code product_skus} 再查一次。
 *       ★ 这也是 {@code mall-review} <b>不需要</b>依赖 {@code mall-product} 的原因。</li>
 * </ol>
 *
 * <p>★★ 归属校验**写死在 SQL 里**（见 {@code OrderItemMapper.xml} 的
 * {@code WHERE o.user_id = #{userId}}）：明细不存在、明细属于别人，
 * 在 SQL 层就<b>合成同一个 {@code null}</b>。调用方拿到的结论天然不可区分 ——
 * 与订单/支付/评价各处的 404 伪装是同一条原则。
 * 这次防线在<b>别人的模块</b>里，所以更要写死在 SQL 里，不能靠调用方自觉。
 *
 * <p>⚠️ 必须挂 {@link NoArgsConstructor}：{@code resultType} 走的是
 * 「反射无参构造 + setter 赋值」的路径，缺了它会在
 * {@code DefaultObjectFactory.create()} 抛 {@code ReflectionException}。
 * <b>编译通过、启动成功，直到真去查一次才炸</b> —— 与 {@code PaymentVO} 同一个坑。
 *
 * <p>★ 全部字段用包装类型：MyBatis 只给「查出来的列」赋 setter，
 * 查不到的字段就留 {@code null} —— 包装类型天然能表达「这里没有值」。
 */
@Data
@NoArgsConstructor
public class OrderItemBuyContext {

    /** 订单明细 id（就是发起评价时客户端传进来的那个 id，原样带回） */
    private Long orderItemId;

    /** 所属订单 id —— ★ 评价表的 order_id 由它派生，客户端不能传 */
    private Long orderId;

    /** 商品 id —— ★ 评价表的 product_id 由它派生，客户端绝不能传（防「一单刷全站」） */
    private Long productId;

    /** SKU id —— 本日评价表不存它，带出来只是为了排障与将来扩展 */
    private Long skuId;

    /** 商品名快照（下单那一刻的值，不 JOIN products） */
    private String productName;

    /** 规格名快照 */
    private String skuName;

    /** 主图快照 */
    private String image;

    /** 订单状态，取值见 {@link com.mallx.order.common.OrderStatus}；★ 评价模块靠它判 {@code COMPLETED} */
    private String orderStatus;
}
