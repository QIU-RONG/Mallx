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
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

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
    public Result<Void> handleValidException(MethodArgumentNotValidException e){
        FieldError fieldError = e.getBindingResult().getFieldError();
        String message = fieldError != null ? fieldError.getDefaultMessage() : "参数校验失败";
        log.warn("参数校验失败: {}",message);
        return Result.error(ResultCode.VALIDATE_FAILED.getCode(),message);
    }

    /**
     * 路径变量 / 查询参数【类型不匹配】：如 {@code GET /api/orders/abc}（id 要 Long，给了字符串）。
     * <p>
     * 【为什么必须单独接一个】
     * Spring 在这种情况抛的是 {@link MethodArgumentTypeMismatchException}，
     * 它是 Exception 的子类但没有更具体的孪生 handler —— 会被下面的
     * {@link #handleException(Exception)} 兜走，客户端收到 200 + code=500
     * 「系统繁忙」，把「调用方传错参数」误报成「服务端故障」，排障时会被带偏。
     * <p>
     * 【为什么返回 200 而不是 HTTP 400】
     * 遵循项目约定：参数类失败统一走「HTTP 200 + body 里的 code」，
     * 前端只需判 code 一处，不用同时处理 HTTP 状态码和业务码两套体系。
     * （Security 层的真实 401/403 是唯一例外，那是过滤器写的响应。）
     */
    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public Result<Void> handleTypeMismatch(MethodArgumentTypeMismatchException e){
        log.warn("参数类型不匹配: name={}, value={}", e.getName(), e.getValue());
        return Result.error(ResultCode.VALIDATE_FAILED.getCode(),
                "参数 " + e.getName() + " 格式不正确");
    }

    /**
     * 【HTTP 方法不被支持】：如 {@code POST /api/products}（该路径只剩 GET 映射）。
     * <p>
     * 【为什么必须单独接一个 —— Day 18 实测发现的真实缺陷】
     * Spring 抛的是 {@link HttpRequestMethodNotSupportedException}，它同样是 Exception 的子类，
     * 会被下面的 {@link #handleException(Exception)} 兜走 ⇒
     * 客户端收到「HTTP 200 + code=500 系统繁忙」，还会在服务端打一条 ERROR 级堆栈。
     * 后果有两个，都不轻：
     * <ol>
     *   <li>「调用方用错了方法」被误报成「服务端故障」，排障方向直接被带偏；</li>
     *   <li>Day 18 迁移 C 端写接口后，本应用 405 证明「路径还在、方法没了」，
     *       被兜成 500 之后就与「路径根本不存在」无法区分 —— 断言失去分辨力。</li>
     * </ol>
     * <p>
     * 【为什么这里用真实 HTTP 405，而不是项目惯用的 200 + code】
     * 405 与 401/403 同类：都是<b>框架/协议层</b>的拒绝，不是业务结果。
     * 业务码那套约定覆盖的是「请求合法、但业务不同意」，方法不被支持连请求都不合法。
     * <b>body 里仍带 code=405</b>，前端沿用「只看 code」的习惯也能工作。
     */
    @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
    @ResponseStatus(HttpStatus.METHOD_NOT_ALLOWED)
    public Result<Void> handleMethodNotSupported(HttpRequestMethodNotSupportedException e){
        log.warn("请求方法不支持: {}", e.getMessage());
        String allow = e.getSupportedHttpMethods() == null
                ? "" : e.getSupportedHttpMethods().toString();
        return Result.error(HttpStatus.METHOD_NOT_ALLOWED.value(), "请求方法不支持，支持的方法：" + allow);
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
