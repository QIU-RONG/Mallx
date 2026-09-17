package com.mallx.admin.security;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.mallx.admin.entity.Admin;
import com.mallx.admin.mapper.AdminMapper;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

/**
 * 管理员账号查询 + 权限拼装。
 * <p>
 * ⚠️ 刻意【不实现】UserDetailsService：
 * 容器里一旦出现 2 个 UserDetailsService Bean，Spring Security 的
 * InitializeUserDetailsBeanManagerConfigurer 会直接放弃装配 DaoAuthenticationProvider，
 * 导致 Day 06 的 C 端登录一起挂掉（详见 Day-07 计划 §6.3）。
 * <p>
 * 所以本类是普通业务类，由 {@code AdminAuthController} 自己调用 findByUsername()，
 * 自己拿 password 做校验，不参与 Security 的自动装配。
 */
@Service
public class AdminAccountService {

    private final AdminMapper adminMapper;

    /** 构造器注入：Spring 启动时把 AdminMapper 塞进来 */
    public AdminAccountService(AdminMapper adminMapper) {
        this.adminMapper = adminMapper;
    }

    /**
     * 按用户名查管理员，并把它的权限码拼成一个扁平集合。
     *
     * @return AdminLoginUser（含 password 原文，供上层用 PasswordEncoder 校验）
     * @throws UsernameNotFoundException 用户名不存在
     */
    public AdminLoginUser findByUsername(String username) {
        // ① 查 admins 表（@TableName("admins") 已生效，注意是复数）
        Admin admin = adminMapper.selectOne(new LambdaQueryWrapper<Admin>()
                .eq(Admin::getUsername, username));
        if (admin == null) {
            throw new UsernameNotFoundException("管理员不存在: " + username);
        }

        // ② 拼权限集合 = 权限码 + 角色码（角色统一加 ROLE_ 前缀）
        List<String> permissions = new ArrayList<>(
                adminMapper.selectPermissionCodesByAdminId(admin.getId()));
        for (String roleCode : adminMapper.selectRoleCodesByAdminId(admin.getId())) {
            permissions.add("ROLE_" + roleCode);   // SUPER_ADMIN → ROLE_SUPER_ADMIN
        }

        // ③ 打包成 UserDetails
        return new AdminLoginUser(admin.getId(), admin.getUsername(),
                admin.getPassword(), admin.getStatus(), permissions);
    }
}
