package com.mallx.common.api;

import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * 统一返回码
 */
@Getter
@AllArgsConstructor
public enum ResultCode {

    SUCCESS(200, "success"),

    FAIL(500, "fail"),

    VALIDATE_FAILED(400, "参数校验失败"),

    UNAUTHORIZED(401, "未登录或登录已过期"),

    FORBIDDEN(403, "没有权限访问"),

    NOT_FOUND(404, "资源不存在"),

    NOT_IMPLEMENTED(501, "功能未实现"),

    /**
     * ★ 手机号未注册（Day 52 · 手机号验证码登录）。
     *
     * <p><b>为什么要一个专属码，而不是复用 404</b>：前端要靠它决定「跳注册页」这个动作。
     * 复用 404 的话，将来任何别的 404 都会被误判成「该去注册」；
     * 用 message 字符串匹配更脆 —— 改一次文案就断。
     * <b>机器要判断的东西，必须有一个稳定的机器可读标识。</b>
     *
     * <p>4xxx 段留给「业务细分码」：首位沿用 HTTP 语义（4 = 客户端侧问题），
     * 后三位是具体业务原因，与上面的通用码不冲突。
     */
    PHONE_NOT_REGISTERED(4041, "该手机号未注册，请先注册");

    private final int code;

    private final String message;
}
