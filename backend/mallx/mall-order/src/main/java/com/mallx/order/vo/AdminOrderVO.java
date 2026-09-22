package com.mallx.order.vo;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 管理端订单列表行（{@code GET /api/admin/orders} 的 records 元素）。
 *
 * <p>★★ 为什么不复用 {@link OrderVO}：
 * <pre>
 *   OrderVO     刻意【不含】userId（内部归属字段不外泄，与 AddressVO 同一条规矩）
 *   AdminOrderVO 恰恰【要】userId + userNickname —— 运营必须知道「这单是谁下的」
 * </pre>
 * 若让 {@code OrderVO} 加上这两个字段来复用，会有两个后果：
 * <ol>
 *   <li><b>C 端接口的响应会跟着变胖</b> —— 一个 VO 同时服务两种可见性，
 *       等于把「出参白名单」这条纪律在同一个类里劈成两半；</li>
 *   <li>将来给管理端加字段（比如下单 IP、风控标记）时，<b>它会顺手泄露给 C 端</b>。</li>
 * </ol>
 * → 显式列一张自己的字段表，就是「出参白名单」最直白的实现：<b>没写在这里的，就出不去</b>。
 *
 * <p>★ 字段集 = 「运营在列表页要做决策所需要的最小信息」：
 * 是谁的单（userId / userNickname）、什么状态（status）、多少钱（payAmount）、
 * 寄给谁（receiverName / receiverPhone）、什么时候下的（createdAt）。
 * <b>不含收货详址与明细</b> —— 列表页不展开，避免 N+1（要看明细请调详情接口）。
 *
 * <p>⚠️ 用作 MyBatis 的 {@code resultType} 时必须有无参构造 ——
 * 框架走的是「反射无参构造 + setter」这条路。
 * {@code @Data} 会生成 setter，但一旦类里出现别的构造函数，
 * Lombok 就不再补默认构造 → 这里显式写 {@code @NoArgsConstructor} 把它钉住。
 * （这个坑编译期不报错，只有真正查库时才炸 {@code ReflectionException}。）
 */
@Data
@NoArgsConstructor
public class AdminOrderVO {

    private Long id;

    private String orderNo;

    /** 买家 id（★ C 端 VO 里刻意没有这一格） */
    private Long userId;

    /** 买家昵称（昵称可空，SQL 侧用 COALESCE 兜底，绝不把裸 NULL 交给前端） */
    private String userNickname;

    private BigDecimal totalAmount;

    private BigDecimal payAmount;

    private String status;

    private String receiverName;

    private String receiverPhone;

    private LocalDateTime createdAt;
}
