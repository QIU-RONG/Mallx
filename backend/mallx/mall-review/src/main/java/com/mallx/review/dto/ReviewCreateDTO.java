package com.mallx.review.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 发表评价的入参（{@code POST /api/reviews}）
 *
 * <p>★★ 本类最要紧的一点是它<b>只有三个字段</b> —— 而且这是<b>结构性的</b>安全设计，
 * 不是「忘了写」：
 *
 * <table border="1">
 *   <caption>谁能决定什么</caption>
 *   <tr><th>字段</th><th>客户端能传？</th><th>服务端怎么来</th></tr>
 *   <tr><td>{@code orderItemId}</td><td>✅ <b>唯一入口</b></td><td>就是它本身</td></tr>
 *   <tr><td>{@code rating}</td><td>✅</td><td>1..5</td></tr>
 *   <tr><td>{@code content}</td><td>✅</td><td>最长 500 字</td></tr>
 *   <tr><td>{@code userId}</td><td>❌ <b>绝不</b></td><td>token 的 principal</td></tr>
 *   <tr><td>{@code orderId}</td><td>❌ <b>绝不</b></td><td>由 orderItemId 反查 order_items</td></tr>
 *   <tr><td>{@code productId}</td><td>❌ ★★ <b>绝不</b></td><td>由 orderItemId 反查 order_items</td></tr>
 *   <tr><td>{@code status}</td><td>❌</td><td>固定写 1</td></tr>
 * </table>
 *
 * <p>★★ 为什么 {@code productId} 绝对不能进这个 DTO：{@code reviews} 对 {@code products}
 * 只有外键（「商品得存在」），<b>没有</b>「你得买过」的约束。
 * 若 {@code product_id} 由客户端传，攻击者只要拿<b>自己一张合法的已完成订单</b>，
 * 就能给<b>任意商品</b>刷五星 —— 一次下单，刷遍全站。
 * 这就是「<b>派生字段原则</b>」最典型的反面教材：
 * <blockquote>凡是服务端能算出来的，就不要让客户端告诉你。</blockquote>
 *
 * <p>★ 做成<b>结构性不可能</b>（DTO 里根本没有这三个字段）之后，
 * 客户端硬塞 {@code userId}/{@code orderId}/{@code productId} 只会被<b>静默忽略</b>
 * —— Spring Boot 默认 {@code FAIL_ON_UNKNOWN_PROPERTIES=false}，
 * 所以验收脚本里专门有一组断言「塞了也没用」（day16-review-e2e.py 第 [9] 组）。
 *
 * <p>⚠️ {@code rating} 必须是<b>包装类型 {@code Integer}</b> 且带 {@code @NotNull}：
 * 写成基本类型 {@code int} 时，{@code rating: null} 会在 <b>Jackson 反序列化阶段</b>就抛
 * {@code HttpMessageNotReadableException} —— 而 {@code GlobalExceptionHandler} 尚未接它，
 * 结果是 {@code code=500}（把「调用方传错」误报成「服务端故障」）。
 * 声明成 Integer + &#64;NotNull 就会规规矩矩落到 {@code MethodArgumentNotValidException} → 400。
 */
@Data
public class ReviewCreateDTO {

    /** ★ 唯一由客户端提供的标识：评的是<u>哪一条订单明细</u>（它把用户/订单/商品三件事一次锁定） */
    @NotNull(message = "订单明细 id 不能为空")
    private Long orderItemId;

    /** 评分 1..5（列无 CHECK 约束，范围只能靠这里守） */
    @NotNull(message = "评分不能为空")
    @Min(value = 1, message = "评分不能低于 1")
    @Max(value = 5, message = "评分不能高于 5")
    private Integer rating;

    /** 评价内容，可空（列是 TEXT 无上限，长度只能靠这里守） */
    @Size(max = 500, message = "评价内容最多 500 字")
    private String content;
}
