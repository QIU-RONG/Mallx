package com.mallx.common.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.mallx.common.api.Result;
import com.mallx.common.api.ResultCode;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.stereotype.Component;

import java.io.IOException;

/**
 * 已认证但权限不足时的出口：返回与业务一致的 {code,message,data} JSON（而不是 Security 默认的 HTML 错误页）。
 * <p>
 * 与 {@link RestAuthenticationEntryPoint} 的分工：
 * <ul>
 *   <li>没登录 / token 无效 → {@link org.springframework.security.core.AuthenticationException} → EntryPoint → 401</li>
 *   <li>登录了但没权限       → {@link AccessDeniedException} → 本类 → 403</li>
 * </ul>
 */
@Component
public class RestAccessDeniedHandler implements AccessDeniedHandler {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    public void handle(HttpServletRequest request,
                       HttpServletResponse response,
                       AccessDeniedException accessDeniedException) throws IOException {
        response.setStatus(HttpServletResponse.SC_FORBIDDEN);             // HTTP 403
        response.setContentType("application/json;charset=UTF-8");        // 不写 charset 中文会乱码
        Result<Void> result = Result.error(ResultCode.FORBIDDEN);
        response.getWriter().write(objectMapper.writeValueAsString(result));
    }
}
