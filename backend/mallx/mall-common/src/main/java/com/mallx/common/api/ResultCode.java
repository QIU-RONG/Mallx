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

    NOT_IMPLEMENTED(501, "功能未实现");

    private final int code;

    private final String message;
}
