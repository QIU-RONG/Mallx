package com.mallx.user.service;

import java.time.Duration;

/**
 * 短信验证码服务（Day 52）。
 *
 * <p><b>它管三件事</b>：生成并发码、60 秒发送限流、校验后一次性作废。
 *
 * <p>★ 为什么用 Redis 而不是数据库表：验证码天然是<b>「短命 + 高频 + 可丢」</b>的数据，
 * 而且「到点自动消失」正是 TTL 的语义 —— 建一张表就得自己写清理任务，
 * 还要防着它无限增长。数据形态决定存储选型。
 *
 * <p>★★ <b>为什么「校验」与「作废」要拆成两步</b>（见 {@link #verify} / {@link #consume}）：
 * 手机号<b>未注册</b>时，登录接口要把用户引导去注册页；
 * 而那个注册动作**还要用同一个验证码**。
 * 如果在「发现未注册」的那一刻就把码消费掉，用户到了注册页会发现码已作废、
 * 又得等 60 秒重发 —— 这是纯粹自己给自己制造的摩擦。
 * ⇒ <b>码只在「本次校验真的换到了东西」（登录成功 / 注册成功）时才作废。</b>
 */
public interface SmsCodeService {

    /**
     * 生成并「发送」验证码。
     *
     * @return <b>开发模式</b>下返回明文验证码，生产环境返回 {@code null}。
     * @throws com.mallx.common.exception.BusinessException 60 秒内重复发送
     */
    String send(String phone);

    /**
     * 校验验证码 —— <b>不</b>作废它。
     *
     * @throws com.mallx.common.exception.BusinessException 码不存在/已过期，或码不正确
     */
    void verify(String phone, String code);

    /** 作废验证码（在本次校验确实要换到结果时才调用） */
    void consume(String phone);

    /**
     * 校验并作废（注册、以及「已注册」的登录走这条）。
     * <p>★ 校验<b>失败</b>时不会作废 —— 否则用户在手机上打错一位就得重新获取，体验很刺眼。
     */
    default void verifyAndConsume(String phone, String code) {
        verify(phone, code);
        consume(phone);
    }

    /** 验证码有效期（对外暴露常量，让测试与文档引用同一份数字，而不是各写各的） */
    Duration CODE_TTL = Duration.ofMinutes(5);

    /** 同一手机号两次发送的最小间隔 */
    Duration SEND_INTERVAL = Duration.ofSeconds(60);
}
