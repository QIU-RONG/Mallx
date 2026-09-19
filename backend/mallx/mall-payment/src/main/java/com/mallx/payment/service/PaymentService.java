package com.mallx.payment.service;

import com.mallx.common.api.PageResult;
import com.mallx.payment.dto.PaymentCreateDTO;
import com.mallx.payment.vo.PaymentVO;

/**
 * 支付服务
 */
public interface PaymentService {

    /**
     * 支付一笔订单（V1.0 模拟支付：调用即成功，不真正调网关）。
     *
     * <p>整个过程在<b>一个事务</b>里：查订单归属 → 读明细 → 插支付单 →
     * CAS 改订单状态 → 逐 SKU {@code locked → sold}。任何一步失败整笔回滚。
     *
     * <p>★★ 「一笔订单只能成功支付一次」这条不变式的<b>唯一</b>保证来自
     * {@code orders} 的条件 UPDATE（{@code WHERE status = 'PENDING_PAYMENT'}），
     * <b>不是</b> {@code payments} 表的唯一索引 ——
     * {@code idx_payments_order_id} 是普通索引，一个订单本来就允许多条支付记录
     * （失败重试 / 换支付方式 / 退款都会产生）。
     *
     * <p>★ 接口形状按真实业务设计：将来把「直接成功」换成「调网关 + 等异步回调」，
     * 只改本方法的实现，上层代码一行都不用动。
     *
     * @param userId 当前登录用户（从 token 来，不接受客户端传参）
     * @throws com.mallx.common.exception.BusinessException code=404 订单不存在；code=400 订单状态不允许支付
     */
    PaymentVO pay(Long userId, PaymentCreateDTO dto);

    /**
     * ★★ 我的支付记录（分页）—— 「我的」这件事靠 <b>JOIN {@code orders}</b> 实现，
     * 因为 {@code payments} 表根本没有 {@code user_id} 列（详见 {@code PaymentMapper}）。
     *
     * <p>★ 分页参数在实现里<b>夹紧</b>后再构造 {@code Page}：
     * {@code page < 1} 归一到 1（防御性，MP 自己也能兜住），
     * {@code size < 1} 归一到 1（★ 必须 —— {@code size=-1} 在 MP 里是「不分页 = 查全表」，
     * {@code size=0} 会返回空列表但 {@code total} 正常，比报错更难发现），
     * {@code size > 100} 截到 100（防 {@code ?size=99999} 一次拖走整张表）。
     *
     * @param userId 当前登录用户（从 token 来）
     * @return 只含本人订单对应的支付记录，按 id 倒序（最新在前）
     */
    PageResult<PaymentVO> listMyPayments(Long userId, long page, long size);

    /**
     * ★ 支付记录详情 —— 不属于当前用户的一律伪装成「不存在」。
     *
     * <p>归属校验写在 SQL 的 {@code AND o.user_id = #{userId}} 里，查不到返回 {@code null}；
     * 本方法把 null 翻译成 404。
     * ★ 「id 不存在」与「id 是别人的」<b>共用同一句错误消息</b>：
     * 若两者可区分，攻击者遍历 id 就能画出「哪些支付记录真实存在」的地图。
     *
     * @param userId    当前登录用户（从 token 来）
     * @param paymentId 支付记录 id
     * @throws com.mallx.common.exception.BusinessException code=404 支付记录不存在
     */
    PaymentVO detailMyPayment(Long userId, Long paymentId);
}
