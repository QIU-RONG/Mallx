package com.mallx.common.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.mallx.common.api.Result;
import com.mallx.common.api.ResultCode;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.stereotype.Component;

import java.io.IOException;

/**
 * 未认证时的出口：返回与业务一致的 {code,message,data} JSON（而不是 Security 默认的 HTML 登录页）。
 */
@Component
public class RestAuthenticationEntryPoint implements AuthenticationEntryPoint {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    public void commence(HttpServletRequest request,
                         HttpServletResponse response,
                         AuthenticationException authException) throws IOException {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);          // HTTP 401
        response.setContentType("application/json;charset=UTF-8");        // 不写 charset 中文会乱码
        Result<Void> body = Result.error(ResultCode.UNAUTHORIZED);
        response.getWriter().write(objectMapper.writeValueAsString(body));
    }
}
