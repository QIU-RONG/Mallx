package com.mallx.admin.vo;

import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 角色详情（{@code GET /api/admin/roles/{id}}，Day 23）—— 多带该角色的权限。
 *
 * <p>与 {@code AdminDetailVO} 是<b>完全同构</b>的一对（同一个「详情多带一组关联」的形状），
 * 平铺而非继承的理由见 {@code AdminDetailVO} 的注释。
 *
 * <p>★ {@code permissionIds} 与 {@code permissionCodes} 都从 {@code role_permissions}
 * <b>关联表</b>现查（{@code selectPermissionIdsByRoleId}）——
 * ⚠️ <b>不要</b>顺手复用 {@code AdminMapper.selectPermissionCodesByAdminId}：
 * 那条是「按管理员查」并<b>穿过两层关联</b>（admin_roles + role_permissions），
 * 而且它（修复后）会按 {@code r.status} 过滤。本方法问的是「这个角色<b>定义</b>了哪些权限」，
 * 与「谁通过它拿到了什么」是两个问题 —— 混用会让「停用角色的详情」看起来权限为空，
 * 而实际上它只是暂时不生效。这是 L2 的教训（{@code getDetail} / {@code getAdminDetail}
 * 必须拆方法：判据不同就不能共用一个方法）。
 *
 * <p>★ 本 VO 是护栏② 的<b>证据来源</b>：验收要证明「SUPER_ADMIN 只许增不许减」，
 * 就得先能读到它当前有哪些权限。
 */
@Data
public class RoleDetailVO {

    private Long id;

    private String name;

    private String code;

    private String description;

    private Integer status;

    private LocalDateTime createdAt;

    /** 该角色当前绑定的权限 id（前端多选框回显用） */
    private List<Long> permissionIds;

    /** 该角色当前绑定的权限码，例 [product:list, role:create]；显示 / 验收断言用 */
    private List<String> permissionCodes;
}
