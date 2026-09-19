package com.mallx.payment.service;

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
}
