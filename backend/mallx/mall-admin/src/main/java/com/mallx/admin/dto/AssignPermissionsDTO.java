package com.mallx.admin.dto;

import jakarta.validation.constraints.NotNull;
import lombok.Data;

import java.util.List;

/**
 * 给角色分配权限（{@code PUT /api/admin/roles/{id}/permissions}，Day 23）。
 *
 * <p>与 {@link AssignRolesDTO} 是<b>完全同构</b>的一对（同一个「全量替换集合」
 * 动作，作用在另一张关联表上）：
 * <ul>
 *   <li>{@code []} = 清空该角色的全部权限；</li>
 *   <li>省略字段（null）= <b>400</b>（{@code @NotNull} 挡下）——
 *       否则「前端漏传」会静默把角色的权限清空；</li>
 *   <li>不存在的 id → <b>400</b>（预校验 count，不靠 FK 的 23503）；</li>
 *   <li>{@code DELETE} + 批量 {@code INSERT} 两条语句 ⇒ 必须 {@code @Transactional}。</li>
 * </ul>
 *
 * <p>★★ <b>护栏② 落在本 DTO 的用途上</b>：若目标是 {@code SUPER_ADMIN} 角色，
 * 目标集合必须是<b>现有集合的超集</b>（只许增、不许减），否则实现侧 400。
 * 为什么允许「增」：将来新增权限码时（本日就新增了 13 条）可以在界面上给超管补授，
 * 不必去改 SQL；冻结反而会逼人绕过接口直接改库 —— 那更糟。
 * 详见 Day-23 文档 §五。
 *
 * <p>⚠️ 注意本 DTO 与<b>权限码只读</b>决策的关系：{@code permissions} 表本身
 * <b>没有</b> CRUD 接口（权限码是代码资产，见 Day-23 文档 §一 决策 1）——
 * 本 DTO 操作的是 {@code role_permissions} <b>关联</b>，不是 {@code permissions} 表。
 */
@Data
public class AssignPermissionsDTO {

    /**
     * 目标权限 id 集合。
     * <p>★ 空数组 = 清空；null = 400；不存在的 id = 400。
     * <p>★ 对 {@code SUPER_ADMIN} 角色：必须是现有集合的超集（护栏②）。
     */
    @NotNull(message = "permissionIds 不能为空（清空请传空数组 []，而不是省略该字段）")
    private List<Long> permissionIds;
}
