package com.mallx.payment.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.mallx.payment.entity.Payment;
import com.mallx.payment.vo.PaymentVO;
import org.apache.ibatis.annotations.Param;

/**
 * 支付记录 Mapper
 *
 * <p>★ 写入（`pay`）仍是纯 BaseMapper：一句无条件的 {@code INSERT} 就够 ——
 * 「一单只成功付一次」的并发防线不在这里，它写在 {@code orders} 的状态条件 UPDATE 上。
 *
 * <p>★★ 但<b>查询必须写 XML</b>（Day 13 第 4 步补）：见下面的 {@link #selectMyPayments}。
 *
 * <p>不加 {@code @Mapper} 注解：全局 {@code @MapperScan("com.mallx.**.mapper")} 已覆盖本包，
 * 且 {@code mall-server} 已依赖 {@code mall-payment}，Bean 会被扫到。
 */
public interface PaymentMapper extends BaseMapper<Payment> {

    /**
     * ★★★ 我的支付记录（分页）—— 全项目第一个「为越权而 JOIN」的查询。
     *
     * <p><b>为什么必须 JOIN：</b>{@code payments} 表只有 9 列
     * （{@code id / payment_no / order_id / amount / method / status / paid_at / created_at / updated_at}），
     * <b>根本没有 {@code user_id}</b> —— 「只查我自己的」这句话在本表上无处可写，
     * 归属条件只能落到 {@code orders.user_id} 上。
     *
     * <p>⚠️ 漏掉 {@code WHERE o.user_id} = 任何登录用户都能拉到<b>全站</b>支付记录，
     * 泄漏金额 + 支付方式 + 支付时间（比订单泄漏更敏感）。实测对照见
     * {@code backend/loadtest/day13-s4-idor-contrast.sql}。
     *
     * <p>★ <b>首参必须是 {@code IPage}</b>：MyBatis-Plus 的 {@code PaginationInnerInterceptor}
     * 靠「方法参数里有没有 {@code IPage}」来决定是否改写 SQL 加 {@code LIMIT/OFFSET} 并跑 count。
     * 少了它<b>不报错，只是静默查全表</b>（返回全部行、{@code total=0}）。
     *
     * <p>★ 第二个参数即使只有一个也必须写 {@code @Param("userId")}，
     * 否则 XML 里的 {@code #{userId}} 解析不到（多参数方法用 {@code arg0/param1} 命名）。
     *
     * @param page   分页参数（由 Service 夹紧后构造）
     * @param userId 当前登录用户（从 token 来，不接受客户端传参）
     */
    IPage<PaymentVO> selectMyPayments(IPage<PaymentVO> page, @Param("userId") Long userId);

    /**
     * ★★ 支付记录详情 —— 归属条件同样写在 SQL 里（{@code AND o.user_id = #{userId}}），
     * 查不到就是 {@code null}，由 Service 统一翻译成 404。
     *
     * <p>★ 为什么<b>不能</b>用 {@code selectById(id)} 再在 Java 里比归属：
     * {@code payments} 没有 {@code user_id} 可比 —— 硬比就得再查一次 {@code orders}，
     * 白多一次往返。归属条件进 SQL 是更短也更难写错的路。
     *
     * @return 属于该用户的记录；不存在 <b>或</b> 属于别人，一律返回 {@code null}
     *         （两种原因在外部必须<b>不可区分</b>，防 id 枚举）
     */
    PaymentVO selectMyPaymentById(@Param("paymentId") Long paymentId,
                                  @Param("userId") Long userId);
}
