package com.mallx.admin.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 编辑角色（{@code PUT /api/admin/roles/{id}}，Day 23）。
 *
 * <p>★ <b>不含 {@code code}</b>，理由与 {@code AdminUpdateDTO} 不含 {@code username}
 * 同构：{@code code} 参与 UNIQUE 约束、且它已经以 {@code ROLE_xxx} 的形式
 * <b>签进了所有已签发 token</b>（路线①的既定后果）—— 改它等于让存量 token 里的
 * 角色位变成孤儿。V1.0 不给改。
 *
 * <p>★★ <b>护栏① 落在本 DTO 的 {@code status} 上</b>：
 * {@code status = 0} 且目标是 {@code SUPER_ADMIN} 角色 → 实现侧必须 400。
 * 为什么这条护栏是硬性的：停用超管角色 = 所有人失去 {@code ROLE_SUPER_ADMIN} +
 * （在 {@code AdminMapper.xml} 那条修复之后）也失去 {@code admin:*} 等全部权限码
 * ⇒ <b>谁也进不来了</b>。详见 Day-23 文档 §五。
 *
 * <p>★ 与 {@code AdminUpdateDTO} 一样：三个字段都可选，但不能全为 null。
 */
@Data
public class RoleUpdateDTO {

    /** 角色显示名；null = 不改 */
    @Size(max = 32, message = "name 最长 32 字符")
    private String name;

    /** 说明；null = 不改 */
    @Size(max = 255, message = "description 最长 255 字符")
    private String description;

    /** 1 = 启用，0 = 停用；null = 不改。★ 目标是 SUPER_ADMIN 且置 0 → 400（护栏①） */
    @Min(value = 0, message = "status 只能是 0（停用）或 1（启用）")
    @Max(value = 1, message = "status 只能是 0（停用）或 1（启用）")
    private Integer status;
}
