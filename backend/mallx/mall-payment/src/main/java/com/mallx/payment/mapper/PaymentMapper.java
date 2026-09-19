package com.mallx.payment.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.mallx.payment.entity.Payment;

/**
 * 支付记录 Mapper
 *
 * <p>本表<b>不需要 XML</b>：写入是一句无条件的 {@code INSERT}（BaseMapper 的 {@code insert} 足够），
 * 「一单只付一次」的并发防线不在这里 —— 它写在 {@code orders} 的状态条件 UPDATE 上（详见 Day 13 规划）。
 * 查询/列表在第 4 步按需加，仍优先用 Wrapper 而不是手写 SQL。
 *
 * <p>不加 {@code @Mapper} 注解：全局 {@code @MapperScan("com.mallx.**.mapper")} 已覆盖本包，
 * 且 {@code mall-server} 已依赖 {@code mall-payment}，Bean 会被扫到。
 */
public interface PaymentMapper extends BaseMapper<Payment> {
}
