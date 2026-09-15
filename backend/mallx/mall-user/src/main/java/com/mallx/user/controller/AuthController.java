package com.mallx.user.controller;


import com.mallx.common.api.Result;
import com.mallx.common.security.JwtProperties;
import com.mallx.common.security.JwtUtil;
import com.mallx.user.dto.LoginDTO;
import com.mallx.user.entity.User;
import com.mallx.user.security.LoginUser;
import com.mallx.user.service.UserService;
import com.mallx.user.vo.LoginVO;
import jakarta.validation.Valid;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
public class AuthController {
    private final AuthenticationManager authenticationManager;
    private final JwtUtil jwtUtil;
    private final JwtProperties jwtProperties;
    private final UserService userService;

    public AuthController(AuthenticationConfiguration configuration, JwtUtil jwtUtil, JwtProperties jwtProperties, UserService userService) {
        this.authenticationManager = configuration.getAuthenticationManager();
        this.jwtUtil = jwtUtil;
        this.jwtProperties = jwtProperties;
        this.userService = userService;
    }

    @PostMapping("/login")
    public Result<LoginVO> login(@RequestBody @Valid LoginDTO loginDTO) {

        // ① 认证：查库 + 比密码 + 判 status 都在 authenticate() 内部完成
        Authentication authentication = authenticationManager.authenticate(
                new UsernamePasswordAuthenticationToken(loginDTO.getUsername(), loginDTO.getPassword()));

        // ② 从认证结果里取出 LoginUser（框架声明是 Object，所以要强转回自己的类型）
        LoginUser loginUser = (LoginUser) authentication.getPrincipal();

        // ③ 签发 token
        String token = jwtUtil.generate(loginUser.getUserId(), loginUser.getUsername());

        // ④ 补查昵称：LoginUser 里没有 nickname 字段
        User user = userService.getById(loginUser.getUserId());

        // ⑤ 组装返回（expireMinutes 是分钟，VO 里的 expiresIn 要的是秒）
        return Result.ok(new LoginVO(
                token,
                "Bearer",
                jwtProperties.getExpireMinutes() * 60,
                loginUser.getUserId(),
                loginUser.getUsername(),
                user != null ? user.getNickname() : null));
    }
}
