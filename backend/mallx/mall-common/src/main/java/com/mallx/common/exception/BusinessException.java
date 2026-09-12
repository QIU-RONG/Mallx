package com.mallx.common.exception;

import com.mallx.common.api.ResultCode;
import lombok.Getter;

/**
 * 业务异常：业务逻辑出错时手动抛出，由全局异常处理器统一捕获返回。
 */
@Getter
public class BusinessException extends RuntimeException {

    /** 业务状态码 */
    private final int code;

    /** 通过 ResultCode 构造（推荐，code 与 message 统一从枚举取） */
    public BusinessException(ResultCode resultCode) {
        super(resultCode.getMessage());
        this.code = resultCode.getCode();
    }

    /** 自定义 code + message */
    public BusinessException(int code, String message) {
        super(message);
        this.code = code;
    }
}
