package com.mallx.common.exception;

import com.mallx.common.api.Result;
import com.mallx.common.api.ResultCode;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@Slf4j
@RestControllerAdvice

public class GlobalExceptionHandler {

    /**
     * 全局异常处理
     * @param e
     * @return
     */
    @ExceptionHandler(BusinessException.class)
    public Result<Void> handleBusinessException(BusinessException e){
        log.warn("业务异常：code={},message={}",e.getCode(), e.getMessage());
        return Result.error(e.getCode(), e.getMessage());
    }


    @ExceptionHandler(MethodArgumentNotValidException.class)
    public Result<Void> handleVaildException(MethodArgumentNotValidException e){
        FieldError fieldError = e.getBindingResult().getFieldError();
        String message = fieldError != null ? fieldError.getDefaultMessage() : "参数校验失败";
        log.warn("参数校验失败: {}",message);
        return Result.error(ResultCode.VALIDATE_FAILED.getCode(),message);
    }

    @ExceptionHandler(Exception.class)
    public Result<Void> handleException(Exception e){
        log.error("系统异常",e);
        return Result.error(ResultCode.FAIL);
    }


    @ExceptionHandler(AuthenticationException.class)
    @ResponseStatus(HttpStatus.UNAUTHORIZED)
    public Result<Void> handleAuthenticationException(AuthenticationException e){
        log.warn("认证异常: {}",e.getMessage());
        return Result.error(ResultCode.UNAUTHORIZED);
    }

    /**
     * 授权失败：@PreAuthorize 拒绝时抛的 AccessDeniedException 专用出口。
     * <p>
     * 【为什么必须单独接一个】
     * 上面的 {@link #handleException(Exception)} 是"什么都接"的兜底，
     * 而 AccessDeniedException 是 RuntimeException 的子类，本来会被它先兜走 ——
     * 结果 @PreAuthorize 拒绝反而返回 200 + code=500，403 永远出不来，
     * RestAccessDeniedHandler 也等不到这个异常。这里声明更具体的类型，Spring 会优先选它。
     * <p>
     * 【为什么还要判匿名】
     * 决定 401 还是 403 的依据是"身份是否成立"，不是异常本身：
     * <ul>
     *   <li>匿名（压根没证明身份）→ 401，提示客户端去登录</li>
     *   <li>已认证但权限不够 → 403</li>
     * </ul>
     * 这和 Spring Security 的 ExceptionTranslationFilter 判定逻辑一致 ——
     * URL 级别的拒绝（如 anyRequest().authenticated()）仍由 RestAccessDeniedHandler 处理，
     * 两个出口返回同样的 JSON 结构，前端不用区分。
     */
    @ExceptionHandler(AccessDeniedException.class)
    public ResponseEntity<Result<Void>> handleAccessDenied(AccessDeniedException e){
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        boolean anonymous = (auth == null || auth instanceof AnonymousAuthenticationToken);
        log.warn("授权失败(anonymous={}) : {}", anonymous, e.getMessage());
        if (anonymous) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body(Result.error(ResultCode.UNAUTHORIZED));
        }
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body(Result.error(ResultCode.FORBIDDEN));
    }
}
