package com.mallx.admin.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 新建角色（{@code POST /api/admin/roles}，Day 23）。
 *
 * <p>★ {@code code} 有 UNIQUE 约束（{@code 01-schema.sql:330}）——
 * 撞车转 <b>400</b>，做法同 {@link AdminCreateDTO} 的注释
 * （{@code ON CONFLICT (code) DO NOTHING RETURNING id}，见
 * {@code AdminRbacMapper#insertRoleIfAbsent}）。
 *
 * <p>★ 为什么给 {@code code} 加 {@code @Pattern} 而不是「爱写啥写啥」：
 * 角色的 {@code code} 会被 {@code AdminAccountService} 加 {@code ROLE_} 前缀
 * 塞进权限集合（{@code SUPER_ADMIN → ROLE_SUPER_ADMIN}）。形如
 * {@code role:super admin}（带空格/冒号）的 code 拼出 {@code ROLE_role:super admin}，
 * 在 {@code SimpleGrantedAuthority} 里不会报错、只是<b>永远匹配不上</b> ——
 * 又一个「错得安静」的形状。格式约束把这类失手挡在入口。
 *
 * <p>⚠️ 允许的形态：大写字母开头，后接大写字母/数字/下划线，长度 2..32
 * （例：{@code SUPER_ADMIN}、{@code D23_TMP_ROLE}、{@code AUDITOR2}）。
 * 刻意<b>不</b>允许小写：种子里三条全是全大写，两套风格混用会让
 * 「按 code 找人」的 SQL（如 {@code 03-data.sql} 的 {@code IN (...)}）变成雷区。
 */
@Data
public class RoleCreateDTO {

    /** 角色显示名，例「商品管理员」 */
    @NotBlank(message = "name 不能为空")
    @Size(max = 32, message = "name 最长 32 字符")
    private String name;

    /** 角色码，UNIQUE；进权限集合时会被加 {@code ROLE_} 前缀 */
    @NotBlank(message = "code 不能为空")
    @Size(min = 2, max = 32, message = "code 长度需在 2..32 之间")
    @Pattern(regexp = "^[A-Z][A-Z0-9_]*$",
            message = "code 只能是大写字母开头的「大写字母 / 数字 / 下划线」组合，例 SUPER_ADMIN")
    private String code;

    /** 说明，可选 */
    @Size(max = 255, message = "description 最长 255 字符")
    private String description;
}
