package com.mallx.user.vo;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 发送验证码的响应（Day 52）。
 *
 * <p>★★ <b>只有一个字段，而且它生产环境永远是 null —— 这一点必须理解清楚</b>
 *
 * <p>{@code devCode} 是「本机 / CI 没有短信服务商」的妥协产物：
 * 验证码没法真的发到手机上，总得有个办法让开发者与自动化测试拿到它。
 * 于是非 prod 环境把它放进响应体，前端直接弹给用户看。
 *
 * <p>⚠️⚠️ <b>生产环境绝不能有这个值</b>（{@code SmsCodeServiceImpl} 用
 * {@code Environment.acceptsProfiles("prod")} 卡住了）。一个会返回验证码的登录接口，
 * 等于没有验证码。接入真实短信服务后，这个字段应当整体删掉。
 *
 * <p>★ 用 VO 而不是直接把 String 塞进 {@code Result<String>}：后者读代码时
 * 完全看不出那个字符串是什么（手机号？令牌？消息？），而 VO 的字段名自己会说话。
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class SmsSendVO {

    /** 仅开发模式有值；生产环境恒为 null */
    private String devCode;
}
