package com.mallx.admin.controller;

import com.mallx.admin.security.AdminAccountService;
import com.mallx.admin.security.AdminLoginUser;
import com.mallx.common.api.Result;
import com.mallx.common.dto.LoginDTO;
import com.mallx.common.security.JwtProperties;
import com.mallx.common.security.JwtUtil;
import com.mallx.common.vo.LoginVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 管理端登录入口。
 * <p>
 * 刻意【不复用】Day 06 的 {@code AuthenticationManager} —— 那条链绑死了 users 表。
 * 这里手动"查人 → 比密码 → 查状态 → 签 token"，与 C 端完全隔离。
 */
@Tag(name = "管理员认证")
@RestController
@RequestMapping("/api/auth/admin")
public class AdminAuthController {

    private final AdminAccountService adminAccountService;
    private final PasswordEncoder passwordEncoder;
    private final JwtUtil jwtUtil;
    private final JwtProperties jwtProperties;

    public AdminAuthController(AdminAccountService adminAccountService,
                               PasswordEncoder passwordEncoder,
                               JwtUtil jwtUtil,
                               JwtProperties jwtProperties) {
        this.adminAccountService = adminAccountService;
        this.passwordEncoder = passwordEncoder;
        this.jwtUtil = jwtUtil;
        this.jwtProperties = jwtProperties;
    }

    @Operation(summary = "管理员登录")
    @PostMapping("/login")
    public Result<LoginVO> adminLogin(@RequestBody @Valid LoginDTO dto) {

        // ① 查人。查不到也统一提示"用户名或密码错误"，不泄露"这个账号是否存在"
        AdminLoginUser admin;
        try {
            admin = adminAccountService.findByUsername(dto.getUsername());
        } catch (UsernameNotFoundException e) {
            throw new BadCredentialsException("用户名或密码错误");
        }

        // ② 比密码：DelegatingPasswordEncoder 按 {noop}/{bcrypt} 前缀自动选算法
        if (!passwordEncoder.matches(dto.getPassword(), admin.getPassword())) {
            throw new BadCredentialsException("用户名或密码错误");
        }

        // ③ ★ 必须手动检查启用状态 —— 绕开了 DaoAuthenticationProvider，它不会帮你查
        //    漏了这一行，status = 0（已禁用）的管理员照样能登录
        if (!admin.isEnabled()) {
            throw new BadCredentialsException("账号已被禁用");
        }

        // ④ 签发 token：把权限集合一并写进 perms claim，过滤器才有东西可还原
        String token = jwtUtil.generateForAdmin(
                admin.getAdminId(), admin.getUsername(), admin.getPermissions());

        // ⑤ 组装返回（expireMinutes 是分钟，VO 的 expiresIn 要秒）
        return Result.ok(new LoginVO(
                token,
                "Bearer",
                jwtProperties.getExpireMinutes() * 60,
                admin.getAdminId(),
                admin.getUsername(),
                "管理员"));
    }
}
